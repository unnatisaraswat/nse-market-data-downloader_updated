import sys

if "--demo" in sys.argv or "--json-source" in sys.argv:
    if "--json-source" in sys.argv:
        sys.argv.remove("--json-source")
    from nse_downloader.cli import main
else:
    from browser_download import main

if __name__ == "__main__":
    raise SystemExit(main())
