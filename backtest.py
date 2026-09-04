name: Backtest

on:
  workflow_dispatch:
    inputs:
      symbols:
        description: "Coinler (virgülle ayır, örn: BTCUSDT,ETHUSDT,SOLUSDT)"
        required: false
        default: "BTCUSDT,ETHUSDT,SOLUSDT"
      days:
        description: "Kaç günlük geçmiş veri test edilsin"
        required: false
        default: "60"

jobs:
  backtest:
    runs-on: ubuntu-latest
    timeout-minutes: 25

    steps:
      - name: Checkout
        uses: actions/checkout@v5

      - name: Setup Python
        uses: actions/setup-python@v6
        with:
          python-version: "3.12"

      - name: Run Backtest
        run: |
          python backtest.py --symbols "${{ github.event.inputs.symbols }}" --days "${{ github.event.inputs.days }}"

      - name: Upload results CSV
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: backtest-results
          path: backtest_results.csv
          if-no-files-found: ignore
