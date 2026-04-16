# A/B Comparison: baseline vs constraint_first

- **Queries:** 5 (sample of 5)
- **Run ID:** `063f7e91`
- **Champion weights:** `{'spec_completeness': 1.0, 'soft_constraint_bonus': 0.1}`
- **Challenger weights:** `{'spec_completeness': 0.5, 'soft_constraint_bonus': 0.3}`

```
Metric                       |     baseline     | constraint_first |   Delta   
-------------------------------------------------------------------------------
Hit Rate@1                   |      0.667       |      0.667       |   +0.000  
Precision@K                  |      0.667       |      0.667       |   +0.000  
Recall@K                     |      1.000       |      1.000       |   +0.000  
NDCG@K                       |      0.667       |      0.667       |   +0.000  
Constraint Sat. Rate         |      1.000       |      1.000       |   +0.000  
Avg Groundedness             |      0.778       |      0.778       |   +0.000  
Avg Citation Accuracy        |      1.000       |      1.000       |   +0.000  
Avg Latency (ms)             |     6378.020     |     6275.203     |  -102.818 
Avg Cost/Query ($)           |      0.000       |      0.000       |   -0.000  
```
