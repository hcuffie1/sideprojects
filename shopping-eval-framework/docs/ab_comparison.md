# A/B Comparison: baseline vs constraint_first

- **Queries:** 18 (full suite)
- **Run ID:** `d81e9a18`
- **Champion weights:** `{'spec_completeness': 1.0, 'soft_constraint_bonus': 0.1}`
- **Challenger weights:** `{'spec_completeness': 0.5, 'soft_constraint_bonus': 0.3}`

```
Metric                       |     baseline     | constraint_first |    Delta    
---------------------------------------------------------------------------------
Hit Rate@1                   |      0.846       |      0.692       |    -0.154   
Precision@K                  |      0.892       |      0.800       |    -0.092   
Recall@K                     |      1.000       |      1.000       |    +0.000   
NDCG@K                       |      0.929       |      0.852       |    -0.077   
Constraint Sat. Rate         |      0.778       |      0.778       |    +0.000   
Avg Groundedness             |      0.982       |      0.875       |    -0.107   
Avg Citation Accuracy        |      0.901       |      0.770       |    -0.131   
Avg Latency (ms)             |     19636.5      |     19218.3      |    -418.3   
Avg Cost/Query ($)           |    $0.001135     |    $0.001221     |  $+0.000086 
```

## Verdict: CHAMPION WINS

- Champion wins: 4
- Challenger wins: 0
- Ties: 2
- Decisive metrics:
  - avg_groundedness: +0.107 for champion
  - avg_citation_accuracy: +0.131 for champion
  - avg_hit_rate_at_1: +0.154 for champion

**Recommendation:** Keep champion. Decisive wins: avg_groundedness: +0.107 for champion; avg_citation_accuracy: +0.131 for champion; avg_hit_rate_at_1: +0.154 for champion.
