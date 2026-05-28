# get_stock_reports test (ASCII only for console)
# Run: python run_reports_test.py

import sys
import io

def main():
    # Force UTF-8 for Windows console
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    log = []
    def out(msg):
        print(msg)
        log.append(msg)
        sys.stdout.flush()

    out("STEP1: import kr_stock_api...")
    try:
        from kr_stock_api import get_stock_reports
        out("STEP1: OK")
    except Exception as e:
        out("STEP1: FAIL - " + str(e))
        with open("run_reports_test_log.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(log))
        sys.exit(1)

    out("STEP2: get_stock_reports(005930)...")
    try:
        result = get_stock_reports("005930")
        out("STEP2: OK")
    except Exception as e:
        out("STEP2: FAIL - " + str(e))
        with open("run_reports_test_log.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(log))
        sys.exit(1)

    out("STEP3: Count = " + str(len(result)))
    out("STEP4: Result = " + str(result))
    with open("run_reports_test_log.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(log))
    out("Done. Log saved to run_reports_test_log.txt")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("FATAL:", e)
        sys.stdout.flush()
        with open("run_reports_test_log.txt", "w", encoding="utf-8") as f:
            f.write("FATAL: " + str(e))
        sys.exit(1)
