# NVDA Trading Assignment

NOTE: Due to my schedule, I was not able to test during trading hours. The order filling code paths is mostly untested.

## Effort Evaluation

This solution took around 7 hrs of work. I realize I initially put too much effort on the actual trading infrastructure and risk management (trade book, positions, hedging) instead of the actual execution strategy, which is why I took a bit longer to build the solution.

## Execution Strategy

The signal we receive is high precision, and indicates a move of at least 50bps in the trade's direction. Since we assume our competitors receive the same signal at the same time as us, we need to be quick at executing.

NVDA is highly liquid, but sending a single large order could cause slippage, thus reducing our profits. To reduce this, I decided to spread our execution over multiple securities which are normally pretty correlated. With the help of an LLM, I came up with the following execution portfolio:

|Asset|Allocation|Order Type|Why?|
|-------|--------|----------|----|
|NVDA	|60%	|Market	|Get immediate exposure.|
|AMD	|20%	|Market	|Moves with NVDA, reduces slippage.|
|QQQ	|10%	|Limit (0.1% from bid)	|High liquidity, can use passive order.|
|SMH	|10%	|Limit (0.1% from bid)	|ETF exposure, spreads risk.|

## Risk Management

To reduce risk for buy orders, I experimented with put option hedging, which matches the buy orders we send out.

There are also risk checks for open exposure and limit order, as well as checks for preventing wash trading.

## Session Recovery

This feature was definitely out-of-scope for this assignment, but I found it useful for testing during non-trading hours. Also I had fun implementing it:P

## Post Trade Analysis

PnL is calculated for all positions. Option PnLs are calculated with expiry taken into consideration for accuracy. For analysing execution quality, we also calculate fill ratio for our orders (which can be useful for analyzing the impact of our competition), as well as slippage.

## Latency

Latency is an important factor in our case. My implementation tries to limit API calls to Alpaca (ex: caching MD data), but there is a lot of room for improvement. In a real system, we would need to consider the entire pipeline, from signal generation to order sending.

## Next Steps

* Proper backtesting
* Deeper analysis of correlated asset basket
* Analyze and reduce latency
* Implementation of longer term strategies
  * VWAP, TWAP