import argparse
import os

import pendulum


cur_dir = os.path.dirname(os.path.abspath(__file__))
drafts_dir = os.path.join(cur_dir, "_drafts")


def create_parser() -> argparse.ArgumentParser:

    parser = argparse.ArgumentParser(description="Create a new draft")

    parser.add_argument("title", metavar="title", type=str, help="Post title")

    return parser


def main():

    parsed = create_parser().parse_args()

    now = pendulum.now()
    day_formatted = now.strftime("%Y-%m-%d")
    day_time_formatted = now.strftime("%Y-%m-%d %H:%M:%S %z")

    title = parsed.title
    title_formatted = "-".join(title.lower().strip().split(" "))

    contents = (
        "---\n"
        "layout: post\n"
        f"title:  \"{title}\"\n"
        f"date: {day_time_formatted}\n"
        "categories: \n"
        "---"
    )

    file_path = os.path.join(drafts_dir, f"{day_formatted}-{title_formatted}.md")

    if os.path.exists(file_path):
        raise RuntimeError(f"{file_path} already exists!")


    with open(file_path, "w") as fd:
        fd.write(contents)


if __name__ == "__main__":
    main()
