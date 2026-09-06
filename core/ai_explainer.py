"""
core/ai_explainer.py  —  ClimateIQ v4
Full academic-grade explanations — detailed, insightful, professional.
"""
from __future__ import annotations
import gc
import json
import urllib.request
from datetime import date
from typing import Dict, Any
import pandas as pd


def _fmt(d) -> str:
    if isinstance(d, date):
        return d.strftime("%d %B %Y")
    return str(d)


def _get_col(df, cmap, k):
    c = cmap.get(k)
    return c if (c and c in df.columns) else None


def _get_data_summary(chart_key: str, df: pd.DataFrame, stats: dict) -> str:
    from core.db_manager import db_manager as _dm
    cmap = _dm._col_map

    if chart_key == "sentiment_donut":
        return (
            f"Positive: {stats.get('positive',0):,} ({stats.get('pos_pct',0)}%), "
            f"Negative: {stats.get('negative',0):,} ({stats.get('neg_pct',0)}%), "
            f"Neutral: {stats.get('neutral',0):,} ({stats.get('neu_pct',0)}%). "
            f"Total: {stats.get('total',0):,}. Avg VADER score: {stats.get('avg_score',0)}."
        )
    elif chart_key == "emotion_bar":
        ec = _get_col(df, cmap, "emotion")
        if ec:
            top = df[ec].value_counts().head(8)
            parts = ", ".join(f"{e}: {n:,}" for e,n in top.items())
            total = top.sum()
            pcts  = ", ".join(f"{e}: {n/total*100:.1f}%" for e,n in top.items())
            return f"Emotion counts: {parts}. Percentages: {pcts}. Dominant: {stats.get('top_emotion','?')}."
        return f"Dominant emotion: {stats.get('top_emotion','?')}."
    elif chart_key == "topic_frequency":
        tc = _get_col(df, cmap, "topic")
        if tc:
            top = df[tc].value_counts().head(10)
            parts = ", ".join(f"{t}: {n:,}" for t,n in top.items())
            total = top.sum()
            pcts  = ", ".join(f"{t}: {n/total*100:.1f}%" for t,n in top.items())
            return f"Topics: {parts}. Percentages: {pcts}."
        return f"Most discussed: {stats.get('top_topic','?')}."
    elif chart_key == "city_comparison":
        cc = _get_col(df, cmap, "city"); sc = _get_col(df, cmap, "sentiment")
        if cc and sc:
            cross = pd.crosstab(df[cc].astype(str), df[sc].str.lower()).fillna(0)
            cross["_t"] = cross.sum(axis=1)
            top5 = cross.nlargest(5,"_t").drop(columns="_t")
            lines=[]
            for city_n, row in top5.iterrows():
                pos_n=int(row.get("positive",0)); neg_n=int(row.get("negative",0)); neu_n=int(row.get("neutral",0))
                tot_n=pos_n+neg_n+neu_n
                if tot_n>0:
                    lines.append(f"{city_n}: {tot_n:,} tweets (pos={pos_n:,}/{pos_n/tot_n*100:.0f}%, neg={neg_n:,}/{neg_n/tot_n*100:.0f}%, neu={neu_n:,}/{neu_n/tot_n*100:.0f}%)")
            return "; ".join(lines) + f". Highest volume: {stats.get('top_city','?')}."
        return f"Top city: {stats.get('top_city','?')}."
    elif chart_key == "score_distribution":
        scc = _get_col(df, cmap, "score")
        if scc:
            s = pd.to_numeric(df[scc], errors="coerce").dropna()
            pos_n = int((s>0.05).sum()); neg_n = int((s<-0.05).sum()); neu_n = int(((s>=-0.05)&(s<=0.05)).sum())
            total = len(s)
            # Find peak bin
            counts, edges = pd.cut(s, bins=20, retbins=True)
            bin_counts = counts.value_counts()
            peak_bin   = bin_counts.index[0]
            return (
                f"Mean: {s.mean():.4f}, Median: {s.median():.4f}, Std: {s.std():.4f}, "
                f"Min: {s.min():.4f}, Max: {s.max():.4f}. "
                f"Positive (>0.05): {pos_n:,} ({pos_n/total*100:.1f}%), "
                f"Negative (<-0.05): {neg_n:,} ({neg_n/total*100:.1f}%), "
                f"Neutral: {neu_n:,} ({neu_n/total*100:.1f}%). "
                f"Most tweets clustered around score range {peak_bin.left:.2f} to {peak_bin.right:.2f}."
            )
        return "VADER scores across all tweets."
    elif chart_key == "daily_activity":
        dc = _get_col(df, cmap, "date")
        if dc:
            try:
                df2 = df.copy()
                df2["_d"] = pd.to_datetime(df2[dc], errors="coerce").dt.date
                daily = df2.groupby("_d").size().sort_index()
                peak_day = daily.idxmax(); peak_n = daily.max()
                low_day  = daily.idxmin(); low_n  = daily.min()
                avg      = daily.mean()
                # Trend: compare first third vs last third
                n = len(daily)
                first_avg = daily.iloc[:n//3].mean() if n>=3 else avg
                last_avg  = daily.iloc[-n//3:].mean() if n>=3 else avg
                trend = "increasing" if last_avg > first_avg * 1.1 else ("decreasing" if last_avg < first_avg * 0.9 else "stable")
                return (
                    f"Total active days: {len(daily)}. Daily average: {avg:.1f} tweets. "
                    f"Peak day: {peak_day} ({peak_n} tweets). "
                    f"Lowest day: {low_day} ({low_n} tweets). "
                    f"Early-period average: {first_avg:.1f}/day, late-period average: {last_avg:.1f}/day. "
                    f"Overall trend: {trend}."
                )
            except Exception: pass
        return f"Daily activity over {stats.get('span_days','?')} days."
    elif chart_key == "weather_breakdown":
        wc = _get_col(df, cmap, "weather")
        if wc:
            counts = df[wc].dropna().astype(str).value_counts().head(8)
            total  = counts.sum()
            parts  = ", ".join(f"{w}: {n:,} ({n/total*100:.1f}%)" for w,n in counts.items())
            return f"Distribution: {parts}."
        return "Weather vs tweet volume breakdown."
    return f"Total: {stats.get('total',0):,} tweets."


# ─────────────────────────────────────────────────────────────────────────────
#  Long academic rule-based explanations
# ─────────────────────────────────────────────────────────────────────────────
def _detailed_explanation(chart_key: str, df: pd.DataFrame, stats: dict,
                           city: str, ds, de) -> str:
    total   = stats.get("total", 0)
    pos_p   = stats.get("pos_pct", 0)
    neg_p   = stats.get("neg_pct", 0)
    neu_p   = stats.get("neu_pct", 0)
    pos_n   = stats.get("positive", 0)
    neg_n   = stats.get("negative", 0)
    neu_n   = stats.get("neutral", 0)
    avg_sc  = stats.get("avg_score", 0)
    span    = stats.get("span_days", 0)
    ds_f    = _fmt(ds); de_f = _fmt(de)

    # Use actual data dates if available
    act_start = stats.get("actual_start")
    act_end   = stats.get("actual_end")
    ds_disp   = _fmt(act_start) if act_start else ds_f
    de_disp   = _fmt(act_end)   if act_end   else de_f

    dom = ("negative" if neg_p>pos_p and neg_p>neu_p
           else "positive" if pos_p>neg_p and pos_p>neu_p
           else "neutral")

    dom_meaning = {
        "negative": "a climate discourse marked by concern, alarm, and pessimism regarding environmental conditions",
        "positive": "a relatively optimistic public outlook on climate and environmental matters",
        "neutral":  "a factual, measured public discourse — tweets are largely informational rather than emotionally charged",
    }[dom]

    from core.db_manager import db_manager as _dm
    cmap = _dm._col_map

    if chart_key == "sentiment_donut":
        score_interp = (
            "strongly negative" if avg_sc < -0.2
            else "mildly negative" if avg_sc < -0.05
            else "neutral" if avg_sc <= 0.05
            else "mildly positive" if avg_sc <= 0.2
            else "strongly positive"
        )
        neg_concern = ""
        if neg_p > 30:
            neg_concern = (
                f" The notably high proportion of negative tweets ({neg_p}%) is particularly significant — "
                f"it indicates that a substantial segment of the public in {city} associates climate-related "
                f"discussion with distress, worry, or dissatisfaction, which may reflect awareness of local "
                f"environmental challenges such as air pollution, extreme heat, or flooding."
            )
        return (
            f"The Sentiment Distribution chart provides a high-level overview of public emotional tone "
            f"across {total:,} climate-related tweets collected from {city} between {ds_disp} and {de_disp} "
            f"— a period spanning {span} days. The pie chart divides all tweets into three sentiment categories: "
            f"Positive ({pos_n:,} tweets, {pos_p}%), Negative ({neg_n:,} tweets, {neg_p}%), and "
            f"Neutral ({neu_n:,} tweets, {neu_p}%). "
            f"The dominant sentiment category is {dom.upper()}, indicating {dom_meaning}. "
            f"The average VADER compound score of {avg_sc:.4f} is classified as {score_interp}, "
            f"on a scale where −1.0 represents extreme negativity and +1.0 represents extreme positivity.{neg_concern} "
            f"It is noteworthy that neutral discourse accounts for {neu_p}% of all tweets, suggesting that "
            f"a large portion of climate-related communication in {city} consists of news sharing, factual reporting, "
            f"or objective commentary rather than personal emotional reactions. "
            f"Overall, this distribution offers researchers and policymakers a clear baseline measure of public "
            f"climate sentiment in {city}, forming the foundation for all subsequent analyses in this report."
        )

    elif chart_key == "emotion_bar":
        top_e = stats.get("top_emotion", "unknown")
        ec    = _get_col(df, cmap, "emotion")
        detail = ""
        if ec:
            top5 = df[ec].value_counts().head(5)
            total_e = top5.sum()
            parts = "; ".join(f"{e.title()} ({n:,} tweets, {n/total_e*100:.1f}%)" for e,n in top5.items())
            detail = f"The top five emotions recorded are: {parts}. "
        return (
            f"The Emotion Category Analysis chart visualises the distribution of specific emotional "
            f"categories detected across {total:,} climate-related tweets from {city} during the period "
            f"{ds_disp} to {de_disp} ({span} days). Unlike the broad positive/negative/neutral classification, "
            f"this chart provides granular insight into the specific nature of the emotional responses "
            f"expressed by the public regarding climate and environmental issues. "
            f"{detail}"
            f"The dominant emotion is '{top_e.title()}', which emerged as the most frequently expressed "
            f"psychological response to climate topics during this study period. "
            f"This finding is significant because it reveals not just that the public has a negative or "
            f"positive attitude, but specifically what kind of concern or feeling drives their engagement "
            f"with climate discourse. "
            f"Emotions such as 'Climate Concern', 'Disaster Risk', and 'Health Hazard' reflect heightened "
            f"awareness of tangible environmental threats, while emotions like 'Resource Crisis' indicate "
            f"concern over long-term sustainability. "
            f"With {neg_p}% of all {total:,} tweets carrying negative sentiment, these emotion categories "
            f"collectively suggest that residents of {city} are acutely aware of environmental degradation, "
            f"and that climate discourse in the region is driven by genuine urgency rather than abstract concern. "
            f"Understanding this emotional landscape is critical for designing targeted climate communication "
            f"and policy interventions in {city}."
        )

    elif chart_key == "topic_frequency":
        top_t  = stats.get("top_topic", "unknown")
        tc     = _get_col(df, cmap, "topic")
        detail = ""
        if tc:
            top6 = df[tc].value_counts().head(6)
            total_t = top6.sum()
            parts = "; ".join(f"{t.title()} ({n:,} tweets, {n/total_t*100:.1f}%)" for t,n in top6.items())
            detail = f"The topic breakdown is as follows: {parts}. "
            if len(top6) == 1:
                detail += (
                    f"Note: All tweets in this dataset share a single topic category ('{top_t.title()}'), "
                    f"which suggests that the dataset was collected specifically around this theme "
                    f"or that the topic classifier assigned a uniform label. "
                )
        return (
            f"The Climate Keyword Frequency chart illustrates which environmental and climate-related "
            f"topics dominated public discourse in {city} during the study period from {ds_disp} to {de_disp}. "
            f"This chart was constructed by analysing the topic labels assigned to each of the {total:,} tweets "
            f"in the dataset, revealing the thematic priorities of online climate conversation. "
            f"{detail}"
            f"The most frequently discussed topic is '{top_t.title()}', which appeared in the greatest "
            f"number of tweets during the {span}-day study window. "
            f"The prominence of specific topics reflects the environmental issues that are most salient "
            f"to the public in {city} — whether driven by recent events, media coverage, or lived experience. "
            f"Topics such as flooding, air quality, and temperature changes tend to spike during or immediately "
            f"after significant weather events, while long-term themes like climate policy and water scarcity "
            f"reflect sustained public concern. "
            f"For policymakers, this chart identifies the areas where public education and intervention "
            f"may be most needed, and for researchers, it offers a window into the evolving thematic landscape "
            f"of climate communication in {city} across the {span}-day period under study."
        )

    elif chart_key == "weather_breakdown":
        wc     = _get_col(df, cmap, "weather")
        detail = ""
        if wc:
            counts = df[wc].dropna().astype(str).value_counts().head(5)
            total_w = counts.sum()
            parts   = "; ".join(f"{w.title()} ({n:,} tweets, {n/total_w*100:.1f}%)" for w,n in counts.items())
            detail  = f"The weather-wise distribution is: {parts}. "
        return (
            f"The Weather Condition Breakdown chart examines the relationship between reported weather "
            f"conditions and tweet activity in {city} across the {span}-day study period "
            f"({ds_disp} to {de_disp}). "
            f"Each segment of the pie chart represents a distinct weather condition under which tweets "
            f"were posted, providing insight into whether extreme or unusual weather drives greater "
            f"public engagement with climate-related discourse. "
            f"{detail}"
            f"This analysis is particularly relevant in the context of {city}, where environmental "
            f"stressors such as smog, heatwaves, and heavy rainfall are known to affect daily life and "
            f"public health. A higher volume of tweets associated with severe weather conditions "
            f"— such as flooding, air pollution, or drought — would suggest that direct environmental "
            f"experience is a key motivator for public climate discussion. "
            f"Conversely, a relatively uniform distribution across weather conditions indicates that "
            f"climate concern in {city} is a persistent, ongoing issue rather than one triggered solely "
            f"by acute weather events. "
            f"With {total:,} total tweets analysed and {neg_p}% carrying negative sentiment, this chart "
            f"helps establish a causal link between atmospheric conditions and the emotional tone of "
            f"climate-related communication in the region."
        )

    elif chart_key == "city_comparison":
        top_c  = stats.get("top_city", city)
        cc     = _get_col(df, cmap, "city"); sc = _get_col(df, cmap, "sentiment")
        detail = ""
        if cc and sc:
            cities_n = df[cc].nunique()
            city_list = ", ".join(df[cc].value_counts().head(5).index.tolist())
            detail = (
                f"The dataset includes {cities_n} unique cit{'y' if cities_n==1 else 'ies'} "
                f"in this analysis. Cities represented: {city_list}. "
            )
        return (
            f"The City-Based Sentiment Comparison chart presents a side-by-side clustered bar "
            f"comparison of positive, negative, and neutral tweet volumes across all cities "
            f"represented in the dataset for the period {ds_disp} to {de_disp}. "
            f"{detail}"
            f"Among all cities analysed, {top_c} recorded the highest overall tweet volume, "
            f"making it the most active hub of climate-related social media discussion during "
            f"the study period. "
            f"The overall sentiment balance across the dataset is {pos_p}% positive ({pos_n:,} tweets), "
            f"{neg_p}% negative ({neg_n:,} tweets), and {neu_p}% neutral ({neu_n:,} tweets). "
            f"The average VADER compound score of {avg_sc:.4f} indicates an overall {dom} lean. "
            f"Geographic comparisons of this nature reveal important regional differences in climate "
            f"awareness and emotional engagement — cities with higher proportions of negative sentiment "
            f"may be experiencing more severe environmental pressures or may have more active climate "
            f"advocacy communities, while cities with more neutral discourse may reflect populations "
            f"that consume climate information in a more detached, informational manner. "
            f"Such city-level insights are valuable for targeted policy design and for understanding "
            f"how local environmental conditions shape the nature of public climate discourse in Pakistan."
        )

    elif chart_key == "score_distribution":
        scc = _get_col(df, cmap, "score")
        detail = ""
        if scc:
            s = pd.to_numeric(df[scc], errors="coerce").dropna()
            pos_vad = int((s>0.05).sum()); neg_vad = int((s<-0.05).sum())
            neu_vad = int(((s>=-0.05)&(s<=0.05)).sum())
            skew    = "right-skewed (more positive extremes)" if s.skew()>0.3 else ("left-skewed (more negative extremes)" if s.skew()<-0.3 else "approximately symmetric")
            detail  = (
                f"Precisely, {pos_vad:,} tweets ({pos_vad/len(s)*100:.1f}%) scored above +0.05 (positive zone), "
                f"{neg_vad:,} tweets ({neg_vad/len(s)*100:.1f}%) scored below −0.05 (negative zone), and "
                f"{neu_vad:,} tweets ({neu_vad/len(s)*100:.1f}%) fell in the neutral range (−0.05 to +0.05). "
                f"The distribution is {skew}. "
                f"Standard deviation: {s.std():.4f}, indicating {'high' if s.std()>0.2 else 'moderate' if s.std()>0.1 else 'low'} "
                f"variability in emotional intensity across tweets. "
            )
        return (
            f"The VADER Score Distribution chart provides the most granular view of sentiment in this "
            f"report, plotting the raw VADER compound score for every one of the {total:,} tweets "
            f"collected from {city} between {ds_disp} and {de_disp}. "
            f"VADER (Valence Aware Dictionary and sEntiment Reasoner) is a rule-based sentiment analysis "
            f"tool specifically designed for social media text. It assigns each tweet a compound score "
            f"ranging from −1.0 (maximally negative) to +1.0 (maximally positive), with scores between "
            f"−0.05 and +0.05 considered neutral. "
            f"The histogram bars are colour-coded: green bars represent positive-scoring tweets, red bars "
            f"represent negative-scoring tweets, and blue bars represent neutral-scoring tweets. "
            f"The amber dashed line marks the mean score of {avg_sc:.4f}. "
            f"{detail}"
            f"The overall distribution pattern reveals how emotionally polarised or concentrated the "
            f"public's response to climate topics is in {city} during this {span}-day period. "
            f"A distribution heavily concentrated in the negative zone suggests widespread climate anxiety, "
            f"while a flatter, more spread-out distribution indicates a diverse range of public reactions "
            f"from alarm to indifference to optimism. "
            f"This chart is particularly useful for researchers seeking to understand not just the "
            f"direction of sentiment, but also its intensity and consistency across the population."
        )

    elif chart_key == "daily_activity":
        dc = _get_col(df, cmap, "date")
        detail = ""
        if dc:
            try:
                df2 = df.copy()
                df2["_d"] = pd.to_datetime(df2[dc], errors="coerce").dt.date
                daily = df2.groupby("_d").size().sort_index()
                peak_day = daily.idxmax(); peak_n = daily.max()
                avg_d    = daily.mean()
                n        = len(daily)
                first_avg = daily.iloc[:n//3].mean() if n>=3 else avg_d
                last_avg  = daily.iloc[-n//3:].mean() if n>=3 else avg_d
                trend     = "an upward trend" if last_avg>first_avg*1.1 else ("a downward trend" if last_avg<first_avg*0.9 else "a relatively stable pattern")
                detail = (
                    f"The data spans {n} active days with a daily average of {avg_d:.1f} tweets. "
                    f"The single most active day was {_fmt(peak_day)}, which recorded {peak_n} tweets — "
                    f"likely corresponding to a significant climate event, news story, or environmental "
                    f"incident in {city} or Pakistan more broadly. "
                    f"Comparing early-period activity ({first_avg:.1f} tweets/day on average) with the "
                    f"later portion of the study ({last_avg:.1f} tweets/day), the data shows {trend} "
                    f"in public climate discourse engagement. "
                )
            except Exception: pass
        return (
            f"The Daily Tweet Activity and Trends chart offers a temporal perspective on climate "
            f"discourse, tracking how public engagement on climate-related topics fluctuated "
            f"day by day across the {span}-day study period from {ds_disp} to {de_disp} in {city}. "
            f"The teal area-line represents the raw daily tweet count, revealing natural fluctuations "
            f"in public engagement. The amber dashed line represents the 7-day rolling average, "
            f"which smooths out short-term noise and highlights medium-term trends in activity levels. "
            f"The orange dotted line on the right axis tracks the average word count per tweet "
            f"over time, providing a proxy for tweet complexity and depth of engagement. "
            f"{detail}"
            f"Spikes in daily activity are particularly informative — they typically indicate "
            f"that a climate-relevant event (such as an extreme weather episode, a government "
            f"policy announcement, or an international climate summit) triggered heightened public "
            f"discussion. Periods of sustained low activity may reflect public fatigue, seasonal "
            f"variation, or reduced media coverage of climate topics. "
            f"Across the full {span} days, {total:,} tweets were recorded, averaging "
            f"{total/max(span,1):.1f} tweets per day, which provides a baseline measure of "
            f"climate-related social media engagement intensity in {city} during this period."
        )

    chart_name = chart_key.replace("_", " ").title()
    return (
        f"The {chart_name} chart presents an analysis of {total:,} climate-related tweets "
        f"from {city} between {ds_disp} and {de_disp} ({span} days). "
        f"The overall sentiment is {dom} — {pos_p}% positive, {neg_p}% negative, {neu_p}% neutral — "
        f"with an average VADER score of {avg_sc:.4f}. "
        f"This chart highlights the key patterns in the data and provides context for understanding "
        f"public climate discourse in {city} during the study period."
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Anthropic API (optional bonus — graceful fallback)
# ─────────────────────────────────────────────────────────────────────────────
def _call_api(prompt: str) -> str:
    try:
        payload = json.dumps({
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 600,
            "messages": [{"role": "user", "content": prompt}]
        }).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages", data=payload,
            headers={"content-type":"application/json","anthropic-version":"2023-06-01"},
            method="POST")
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())["content"][0]["text"].strip()
    except Exception:
        return ""


# ─────────────────────────────────────────────────────────────────────────────
#  Public API
# ─────────────────────────────────────────────────────────────────────────────
def generate_explanation(chart_key, df, stats, city, ds, de) -> str:
    # Try Anthropic API first
    data_summary = _get_data_summary(chart_key, df, stats)
    act_start = stats.get("actual_start"); act_end = stats.get("actual_end")
    ds_disp = _fmt(act_start) if act_start else _fmt(ds)
    de_disp = _fmt(act_end)   if act_end   else _fmt(de)

    prompt = (
        f"You are an academic climate data analyst writing a professional research report.\n"
        f"Write a detailed analytical paragraph (8-10 sentences, formal academic English, no bullet points, no headers) "
        f"explaining this chart with deep insights, trend analysis, and policy implications.\n\n"
        f"Chart: {chart_key.replace('_',' ').title()}\n"
        f"City: {city} | Period: {ds_disp} to {de_disp} | Total tweets: {stats.get('total',0):,}\n"
        f"Sentiment: {stats.get('pos_pct',0)}% positive, {stats.get('neg_pct',0)}% negative, {stats.get('neu_pct',0)}% neutral\n"
        f"Key data: {data_summary}\n\n"
        f"Write a thorough professional paragraph:"
    )
    api_result = _call_api(prompt)
    if api_result and len(api_result.split()) >= 60:
        return api_result

    # Always works — detailed rule-based
    return _detailed_explanation(chart_key, df, stats, city, ds, de)


def generate_all_explanations(charts, stats, df, city, ds, de,
                               progress_callback=None):
    explanations = {}
    keys  = list(charts.keys())
    total = len(keys)
    for idx, key in enumerate(keys):
        if progress_callback:
            try: progress_callback(idx, total, key)
            except Exception: pass
        explanations[key] = generate_explanation(key, df, stats, city, ds, de)
        gc.collect()
    return explanations
