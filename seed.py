from nasa import import_apod_range, import_neows_range, import_search_results
from db import init_db


FULL_QUERIES_IMG = [
    "hubble",
    "james webb",
    "mars perseverance",
    "apollo",
    "nebula",
    "saturn",
    "earth",
    "moon",
    "galaxy",
    "supernova",
]

FULL_QUERIES_VID = ["mars", "international space station", "launch", "spacewalk"]

REDUCED_QUERIES_IMG = ["hubble", "james webb", "mars perseverance", "nebula"]
REDUCED_QUERIES_VID = ["mars", "international space station"]


def run_full_seed(progress_callback=None, reduced=False) -> None:
    init_db()

    if reduced:
        queries_img = REDUCED_QUERIES_IMG
        img_count = 20
        queries_vid = REDUCED_QUERIES_VID
        vid_count = 10
        apod_days = 7
        neo_days = 7
    else:
        queries_img = FULL_QUERIES_IMG
        img_count = 50
        queries_vid = FULL_QUERIES_VID
        vid_count = 20
        apod_days = 30
        neo_days = 14

    total_steps = len(queries_img) + len(queries_vid) + 2
    current = 0

    def report():
        nonlocal current
        current += 1
        if progress_callback:
            progress_callback(current, total_steps)

    for q in queries_img:
        import_search_results(q, "image", img_count)
        report()

    for q in queries_vid:
        import_search_results(q, "video", vid_count)
        report()

    import_apod_range(apod_days)
    report()

    import_neows_range(neo_days)
    report()


def main() -> None:
    print("initializing database")
    run_full_seed()
    print("seed completed")


if __name__ == "__main__":
    main()