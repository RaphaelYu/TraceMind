# Error Codes

| Code            | When                                     | Retry? |
|-----------------|------------------------------------------|--------|
| BAD_REQUEST     | Missing params, bad template vars        | No     |
| RUN_TIMEOUT     | Step timeout hit                          | Yes    |
| RUN_CANCELLED   | Task cancelled                            | No     |
| PROVIDER_ERROR  | Transport/unknown provider failure        | Yes    |
| RATE_LIMIT      | 429-like throttling                       | Yes    |
| QUEUE_TIMEOUT   | Local queue/backpressure timeout          | Yes    |
