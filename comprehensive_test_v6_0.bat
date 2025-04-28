@echo off
REM =======================================================
REM Synonym Brain v6.0 Comprehensive Test Suite
REM =======================================================
echo.
if not exist "test_results" mkdir test_results

echo Basic regression (100 questions)...
python test_harness_v6_0.py --server-script local_bot_server_v6_0.py --start-server --test-size 100 --output-folder ./test_results/basic
echo.

FOR %%C IN ("Remaining qty" "Dealer net price \n[USD]" "Product family" "Customer" "End date") DO (
    echo Category test %%C ...
    python test_harness_v6_0.py --server-script local_bot_server_v6_0.py --start-server --test-size 100 --category %%C --output-folder ./test_results/%%C
    echo.
)

echo Brain validation (500 questions)...
python brain_validator_v6_0.py --brain-file golden_brain_v6_0.py --test-size 500 --output-folder ./test_results/brain_validation
echo.

echo Multi‑model comparison...
python multi_model_tester_v6_0.py --server-script local_bot_server_v6_0.py --test-script test_harness_v6_0.py --questions-per-model 150 --models mistral mixtral openchat --output-folder ./test_results/model_comparison --force-shutdown
echo.

echo Regression 1000 vs baseline...
python test_harness_v6_0.py --server-script local_bot_server_v6_0.py --start-server --test-size 1000 --output-folder ./test_results/regression --compare-with ./test_results/v3.9.2/summary_latest.md
echo.

echo Benchmark run (200)...
python test_harness_v6_0.py --server-script local_bot_server_v6_0.py --start-server --test-size 200 --benchmark --output-folder ./test_results/benchmark
echo.

echo Generating comprehensive report...
python generate_test_report.py --input-folder ./test_results --output-file ./test_results/comprehensive_report.md
echo.
echo All tests done!  Report at test_results\\comprehensive_report.md
