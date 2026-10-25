"""Profile a HawkeyeStats CSV. Usage: python -I profile.py <csv>"""

import sys
import pandas as pd

df = pd.read_csv(sys.argv[1])
print(df.shape)
print(df.dtypes.to_string())
print("\nnull %\n", (df.isna().mean() * 100).round(1).to_string())
print("\nnunique matchId", df.matchId.nunique(), "min/max", df.matchId.min(), df.matchId.max())
num = [
    "ballSpeed",
    "pitchX",
    "pitchY",
    "stumpsX",
    "stumpsY",
    "fieldX",
    "fieldY",
    "runs",
    "batterRuns",
    "extras",
]
print(df[num].describe(percentiles=[0.01, 0.05, 0.5, 0.95, 0.99]).round(2).T.to_string())
print(df.head(8).T.to_string())
print(df.bowlingStyle.value_counts().head(15).to_string())
print(df.dismissalDetails.dropna().head(5).tolist())
print(df.ball.value_counts().sort_index().to_string())
