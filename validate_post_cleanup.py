import json

import feedparser


def main():
    config_path = 'config/feeds.txt'
    output_path = 'output/artifacts/feed_validation_post_cleanup.json'
    
    try:
        with open(config_path) as f:
            urls = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
    except FileNotFoundError:
        print(f"Error: {config_path} not found")
        return

    results = []
    total_active = len(urls)
    total_pass = 0
    total_fail = 0
    failed_details = []

    for url in urls:
        fail_reason = None
        try:
            d = feedparser.parse(url)
            if d.get('bozo') and not d.entries:
                fail_reason = str(d.get('bozo_exception', 'Bozo error with no entries'))
            elif not d.entries:
                fail_reason = "No entries found"
            else:
                has_date = False
                for entry in d.entries:
                    if (entry.get('published_parsed') or entry.get('updated_parsed')):
                        has_date = True
                        break
                if not has_date:
                    fail_reason = "No dated entries (published/updated)"
        except Exception as e:
            fail_reason = str(e)

        if fail_reason:
            total_fail += 1
            failed_details.append({"url": url, "error": fail_reason})
            results.append({"url": url, "status": "fail", "error": fail_reason})
        else:
            total_pass += 1
            results.append({"url": url, "status": "pass"})

    report = {
        "summary": {
            "TOTAL_ACTIVE": total_active,
            "TOTAL_PASS": total_pass,
            "TOTAL_FAIL": total_fail
        },
        "failed_urls": failed_details,
        "details": results
    }

    with open(output_path, 'w') as f:
        json.dump(report, f, indent=4)

    print(f"TOTAL_ACTIVE: {total_active}")
    print(f"TOTAL_PASS: {total_pass}")
    print(f"TOTAL_FAIL: {total_fail}")
    if failed_details:
        print("\nFailed URLs:")
        for item in failed_details:
            print(f"- {item['url']}: {item['error']}")

if __name__ == "__main__":
    main()
