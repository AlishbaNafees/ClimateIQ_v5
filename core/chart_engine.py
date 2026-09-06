"""
core/chart_engine.py  —  ClimateIQ v4
Clean, readable charts for non-technical users.
"""
from __future__ import annotations
import io
from typing import Dict, Tuple
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates
from matplotlib.figure import Figure
import pandas as pd
import numpy as np

_POS="_POS"; _NEG="#EF4444"; _NEU="#60A5FA"
_POS="#22C55E"; _TEAL="#14B8A6"; _ORNG="#F97316"; _AMBER="#F59E0B"
_PURP="#A78BFA"; _PINK="#EC4899"
_BG="#0F172A"; _AX="#1E293B"; _GRID="#334155"; _TXT="#E2E8F0"; _TXT2="#94A3B8"
_PALETTE=[_TEAL,_PURP,_ORNG,_POS,_NEG,_AMBER,_PINK,_NEU,"#38BDF8","#A3E635"]

def _sa(ax,title="",xlabel="",ylabel=""):
    ax.set_facecolor(_AX)
    for s in ax.spines.values(): s.set_edgecolor(_GRID)
    ax.tick_params(colors=_TXT,labelsize=9,length=4)
    ax.xaxis.label.set_color(_TXT2); ax.xaxis.label.set_fontsize(10)
    ax.yaxis.label.set_color(_TXT2); ax.yaxis.label.set_fontsize(10)
    if xlabel: ax.set_xlabel(xlabel)
    if ylabel: ax.set_ylabel(ylabel)
    if title: ax.set_title(title,color=_TXT,fontsize=13,fontweight="bold",pad=12)
    ax.grid(axis="y",color=_GRID,linestyle="--",linewidth=0.6,alpha=0.7)
    ax.set_axisbelow(True)

def _fig(w=10,h=5.5):
    f,ax=plt.subplots(figsize=(w,h)); f.patch.set_facecolor(_BG); return f,ax

def _bytes(fig):
    buf=io.BytesIO()
    fig.savefig(buf,format="png",bbox_inches="tight",facecolor=fig.get_facecolor(),dpi=130)
    buf.seek(0); data=buf.read(); plt.close(fig); return data

def _col(df,cmap,k):
    c=cmap.get(k)
    return c if (c and c in df.columns) else None

def _sentiment_donut(df,cmap):
    sc=_col(df,cmap,"sentiment")
    counts=df[sc].str.lower().value_counts() if sc else pd.Series({"neutral":len(df)})
    order=[l for l in ["positive","negative","neutral"] if l in counts.index]
    counts=counts.reindex(order).dropna()
    clrs=[{"positive":_POS,"negative":_NEG,"neutral":_NEU}[l] for l in counts.index]
    f,ax=_fig(8,5.5); _sa(ax,title="Sentiment Distribution"); ax.set_facecolor(_BG)
    wedges,_,autotexts=ax.pie(counts.values,labels=None,colors=clrs,autopct="%1.1f%%",
        startangle=90,pctdistance=0.72,wedgeprops=dict(edgecolor=_BG,linewidth=2.5),
        textprops=dict(color=_TXT,fontsize=10))
    for at in autotexts: at.set_fontsize(11); at.set_fontweight("bold")
    ax.legend(wedges,[f"{l.title()}  —  {v:,} tweets" for l,v in zip(counts.index,counts.values)],
        loc="lower center",bbox_to_anchor=(0.5,-0.12),ncol=len(counts),fontsize=9,framealpha=0,labelcolor=_TXT)
    total=counts.sum()
    ax.text(0,0.05,f"{total:,}",ha="center",va="center",color=_TXT,fontsize=16,fontweight="bold")
    ax.text(0,-0.18,"tweets",ha="center",va="center",color=_TXT2,fontsize=9)
    f.tight_layout(); return f,_bytes(f)

def _emotion_bar(df,cmap):
    ec=_col(df,cmap,"emotion")
    counts=df[ec].str.lower().value_counts().head(8) if ec else pd.Series({"no data":len(df)})
    f,ax=_fig(10,5.5); _sa(ax,title="Emotion Category Breakdown",xlabel="Number of Tweets",ylabel="Emotion")
    emotions=[str(e).replace("_"," ").title() for e in counts.index]
    values=counts.values.tolist(); clrs=_PALETTE[:len(emotions)]
    bars=ax.barh(emotions,values,color=clrs,height=0.55,edgecolor=_BG,linewidth=0.8)
    maxv=max(values) if values else 1
    for bar,val in zip(bars,values):
        ax.text(bar.get_width()+maxv*0.015,bar.get_y()+bar.get_height()/2,
            f"{val:,}",va="center",ha="left",color=_TXT,fontsize=9,fontweight="bold")
    ax.invert_yaxis(); ax.set_xlim(0,maxv*1.18)
    ax.grid(axis="x",color=_GRID,linestyle="--",linewidth=0.6,alpha=0.7); ax.grid(axis="y",visible=False)
    f.tight_layout(); return f,_bytes(f)

def _topic_frequency(df,cmap):
    tc=_col(df,cmap,"topic")
    counts=df[tc].str.lower().value_counts().head(10) if tc else pd.Series({"general":len(df)})
    topics=[str(t).replace("_"," ").title() for t in counts.index]
    values=counts.values.tolist()
    f,ax=_fig(10,5.5); _sa(ax,title="Most Discussed Climate Topics",xlabel="Topic",ylabel="Number of Tweets")
    clrs=_PALETTE[:len(topics)]
    bars=ax.bar(range(len(topics)),values,color=clrs,edgecolor=_BG,linewidth=0.8,width=0.6)
    maxv=max(values) if values else 1
    for bar,val in zip(bars,values):
        ax.text(bar.get_x()+bar.get_width()/2,bar.get_height()+maxv*0.012,
            f"{val:,}",ha="center",va="bottom",color=_TXT,fontsize=8,fontweight="bold")
    ax.set_xticks(range(len(topics))); ax.set_xticklabels(topics,rotation=30,ha="right",fontsize=9)
    ax.set_ylim(0,maxv*1.15); f.tight_layout(); return f,_bytes(f)

def _weather_breakdown(df,cmap):
    wc=_col(df,cmap,"weather")
    if wc:
        raw=df[wc].dropna().astype(str).str.strip()
        raw=raw[raw.str.lower()!="unknown"]
        counts=raw.value_counts().head(8)
    else: counts=pd.Series()
    if counts.empty: counts=pd.Series({"No weather data":len(df)})
    labels=[str(l).title() for l in counts.index]
    values=counts.values.tolist(); clrs=_PALETTE[:len(labels)]
    f,ax=_fig(9,5.5); _sa(ax,title="Tweet Volume by Weather Condition"); ax.set_facecolor(_BG)
    wedges,_,autotexts=ax.pie(values,labels=None,colors=clrs,autopct="%1.1f%%",startangle=120,
        pctdistance=0.75,wedgeprops=dict(edgecolor=_BG,linewidth=2),textprops=dict(color=_TXT,fontsize=10))
    for at in autotexts: at.set_fontsize(9); at.set_fontweight("bold")
    ncol=min(4,len(labels))
    ax.legend(wedges,[f"{l}  ({v:,})" for l,v in zip(labels,values)],
        loc="lower center",bbox_to_anchor=(0.5,-0.14),ncol=ncol,fontsize=8.5,framealpha=0,labelcolor=_TXT)
    f.tight_layout(); return f,_bytes(f)

def _city_comparison(df,cmap):
    cc=_col(df,cmap,"city"); sc=_col(df,cmap,"sentiment")
    if cc and sc:
        cross=pd.crosstab(df[cc].astype(str),df[sc].str.lower()).fillna(0)
        cross["_t"]=cross.sum(axis=1); cross=cross.nlargest(10,"_t").drop(columns="_t")
    else: cross=pd.DataFrame({"neutral":[len(df)]},index=["All"])
    cities=[str(c) for c in cross.index]
    cols_show=[c for c in ["positive","negative","neutral"] if c in cross.columns]
    col_colors={"positive":_POS,"negative":_NEG,"neutral":_NEU}
    n=len(cols_show); x=np.arange(len(cities)); w=0.7/max(n,1)
    f,ax=_fig(max(9,len(cities)*1.1),5.5)
    _sa(ax,title="City-Wise Sentiment Comparison",xlabel="City",ylabel="Number of Tweets")
    for i,col in enumerate(cols_show):
        off=(i-n/2+0.5)*w
        rects=ax.bar(x+off,cross[col].values,width=w*0.88,label=col.title(),
            color=col_colors[col],edgecolor=_BG,linewidth=0.6)
        for r in rects:
            h=r.get_height()
            if h>0: ax.text(r.get_x()+r.get_width()/2,h+2,f"{int(h):,}",
                ha="center",va="bottom",color=_TXT,fontsize=7)
    ax.set_xticks(x); ax.set_xticklabels(cities,rotation=30,ha="right",fontsize=9)
    ax.legend(framealpha=0,labelcolor=_TXT,fontsize=9,loc="upper right")
    f.tight_layout(); return f,_bytes(f)

def _score_distribution(df,cmap):
    scc=_col(df,cmap,"score")
    scores=pd.to_numeric(df[scc],errors="coerce").dropna() if scc else pd.Series([0.0]*len(df))
    f,ax=_fig(10,5.5)
    _sa(ax,title="VADER Sentiment Score Distribution",
        xlabel="VADER Compound Score  (−1=very negative, +1=very positive)",ylabel="Number of Tweets")
    n_bins=40
    counts,edges=np.histogram(scores,bins=n_bins)
    for cnt,l,r in zip(counts,edges[:-1],edges[1:]):
        mid=(l+r)/2
        clr=_POS if mid>0.05 else (_NEG if mid<-0.05 else _NEU)
        ax.bar(mid,cnt,width=(r-l)*0.88,color=clr,edgecolor=_BG,linewidth=0.4,alpha=0.85)
    mean_val=float(scores.mean())
    ax.axvline(mean_val,color=_AMBER,linewidth=2,linestyle="--",label=f"Mean: {mean_val:.3f}")
    ax.axvline(0.05,color=_POS,linewidth=1.2,linestyle=":",alpha=0.7,label="Positive threshold")
    ax.axvline(-0.05,color=_NEG,linewidth=1.2,linestyle=":",alpha=0.7,label="Negative threshold")
    ax.legend(framealpha=0.1,labelcolor=_TXT,fontsize=8.5,facecolor=_AX,edgecolor=_GRID)
    ymax=ax.get_ylim()[1]
    ax.text(-0.6,ymax*0.92,"NEGATIVE",color=_NEG,fontsize=8,alpha=0.6,fontweight="bold")
    ax.text(0.12,ymax*0.92,"POSITIVE",color=_POS,fontsize=8,alpha=0.6,fontweight="bold")
    f.tight_layout(); return f,_bytes(f)

def _daily_activity(df,cmap):
    dc=_col(df,cmap,"date"); txc=_col(df,cmap,"text")
    f,ax1=_fig(11,5.5)
    _sa(ax1,title="Daily Tweet Activity Over Time",xlabel="Date",ylabel="Tweets per Day")
    if dc:
        try:
            df2=df.copy()
            df2["_dt"]=pd.to_datetime(df2[dc],errors="coerce")
            df2=df2.dropna(subset=["_dt"])
            df2["_date_only"]=df2["_dt"].dt.date
            daily=df2.groupby("_date_only").size().reset_index(name="count")
            daily["_date_only"]=pd.to_datetime(daily["_date_only"])
            daily=daily.sort_values("_date_only")
            ax1.fill_between(daily["_date_only"],daily["count"],alpha=0.20,color=_TEAL)
            ax1.plot(daily["_date_only"],daily["count"],color=_TEAL,linewidth=2,label="Tweets / Day")
            if len(daily)>=7:
                daily["r7"]=daily["count"].rolling(7,min_periods=1).mean()
                ax1.plot(daily["_date_only"],daily["r7"],color=_AMBER,linewidth=1.8,
                    linestyle="--",alpha=0.85,label="7-day average")
            lines2,labels2=[],[]
            if txc:
                df2["_wc"]=df2[txc].astype(str).apply(lambda x:len(x.split()))
                wc=df2.groupby("_date_only")["_wc"].mean().reset_index()
                wc["_date_only"]=pd.to_datetime(wc["_date_only"])
                wc=wc.sort_values("_date_only")
                ax2=ax1.twinx(); ax2.set_facecolor(_AX)
                ax2.plot(wc["_date_only"],wc["_wc"],color=_ORNG,linewidth=1.5,linestyle="-.",
                    alpha=0.75,label="Avg Words/Tweet")
                ax2.set_ylabel("Avg Words per Tweet",color=_ORNG,fontsize=10)
                ax2.tick_params(colors=_ORNG,labelsize=9)
                for s in ax2.spines.values(): s.set_edgecolor(_GRID)
                ax2.spines["right"].set_edgecolor(_ORNG)
                lines2,labels2=ax2.get_legend_handles_labels()
            ax1.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%b %Y"))
            ax1.xaxis.set_major_locator(matplotlib.dates.AutoDateLocator(minticks=4,maxticks=12))
            l1,lb1=ax1.get_legend_handles_labels()
            ax1.legend(l1+lines2,lb1+labels2,framealpha=0.1,labelcolor=_TXT,fontsize=9,
                facecolor=_AX,edgecolor=_GRID,loc="upper left")
            f.autofmt_xdate(rotation=30,ha="right")
        except Exception as exc:
            ax1.text(0.5,0.5,f"Chart error:\n{exc}",ha="center",va="center",
                color=_NEG,fontsize=9,transform=ax1.transAxes)
    else:
        ax1.text(0.5,0.5,"No date column found",ha="center",va="center",color=_TXT2,fontsize=11,transform=ax1.transAxes)
    f.tight_layout(); return f,_bytes(f)

def generate_all_charts(df:pd.DataFrame)->Dict[str,Tuple[Figure,bytes]]:
    from core.db_manager import db_manager as _dm
    cmap=_dm._col_map
    builders=[("sentiment_donut",_sentiment_donut),("emotion_bar",_emotion_bar),
        ("topic_frequency",_topic_frequency),("weather_breakdown",_weather_breakdown),
        ("city_comparison",_city_comparison),("score_distribution",_score_distribution),
        ("daily_activity",_daily_activity)]
    results={}
    for key,fn in builders:
        try: results[key]=fn(df,cmap)
        except Exception as exc:
            f,ax=_fig(9,5); _sa(ax,title=key.replace("_"," ").title())
            ax.text(0.5,0.5,f"Error:\n{exc}",ha="center",va="center",color=_NEG,
                fontsize=9,transform=ax.transAxes)
            results[key]=(f,_bytes(f))
    return results
