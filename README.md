# NVDA Trading Assignment

This repository contains a Docker Compose stack with Redis and a signal mocking service for NVDA trading signals.

## Setup

1. Clone this repository
2. Run `docker compose up` to start the stack

## Components

- Redis container storing signals in the 'nvda' stream
- Signal mock service generating random buy/sell signals for NVDA during market hours

## Signal Format

Signals appear in the Redis stream 'nvda' with the following fields:
- Ticker: NVDA
- Direction: "b" (buy) or "s" (sell)

Signals are generated randomly during US market hours (9:30 AM - 4:00 PM ET) with a 0.5% probability each second.