import html
import os
import random
import re
import shutil
import string
from configparser import RawConfigParser
from glob import glob
from json import dumps
from os.path import isfile
from time import strptime, localtime, time, strftime
from typing import Dict, List, Tuple

from PIL import Image
from jinja2 import Environment, FileSystemLoader, TemplateNotFound

from build_rss_feed import build_rss_feed

JINJA_ENVIRONMENT = Environment(
    loader=FileSystemLoader("src/templates")
)
AUTOGENERATE_WARNING = """<!--
!! DO NOT EDIT THIS FILE !!
It is auto-generated and any work you do here will be replaced the next time this page is generated.
If you want to edit any of these files, edit their *.tpl versions in src/templates.
-->
"""
COMIC_TITLE = ""
BASE_DIRECTORY = os.path.basename(os.getcwd())
LINKS_LIST = []


def path(rel_path: str):
    if rel_path.startswith("/"):
        return "/" + BASE_DIRECTORY + rel_path
    return rel_path


def get_links_list(comic_info: RawConfigParser):
    link_list = []
    for option in comic_info.options("Links Bar"):
        link_list.append({"name": option, "url": path(comic_info.get("Links Bar", option))})
    return link_list


def get_pages_list(comic_info: RawConfigParser):
    page_list = []
    for option in comic_info.options("Pages"):
        page_list.append({"template_name": option, "title": path(comic_info.get("Pages", option))})
    return page_list


def delete_output_file_space(comic_info: RawConfigParser=None):
    shutil.rmtree("comic", ignore_errors=True)
    if os.path.isfile("feed.xml"):
        os.remove("feed.xml")
    if comic_info is None:
        comic_info = read_info("your_content/comic_info.ini")
    for page in get_pages_list(comic_info):
        if os.path.isfile(page["template_name"] + ".html"):
            os.remove(page["template_name"] + ".html")


def setup_output_file_space(comic_info: RawConfigParser):
    # Clean workspace, i.e. delete old files
    delete_output_file_space(comic_info)
    # Create directories if needed
    os.makedirs("comic", exist_ok=True)


def read_info(filepath, to_dict=False, might_be_scheduled=True):
    if might_be_scheduled and not isfile(filepath):
        scheduled_files = glob(filepath + ".*")
        if not scheduled_files:
            raise FileNotFoundError(filepath)
        filepath = scheduled_files[0]
    with open(filepath) as f:
        info_string = f.read()
    if not re.search("^\[.*?\]", info_string):
        # print(filepath + " has no section")
        info_string = "[DEFAULT]\n" + info_string
    info = RawConfigParser()
    info.optionxform = str
    info.read_string(info_string)
    if to_dict:
        # TODO: Support multiple sections
        if not list(info.keys()) == ["DEFAULT"]:
            raise NotImplementedError("Configs with multiple sections not yet supported")
        return dict(info["DEFAULT"])
    return info


def schedule_files(folder_path):
    for filepath in glob(folder_path + "/*"):
        if not re.search(r"\.[a-z]{10}$", filepath):
            # Add an extra extension to the filepath, a period followed by ten random lower case characters
            os.rename(filepath, filepath + "." + "".join(random.choices(string.ascii_lowercase, k=10)))


def unschedule_files(folder_path):
    for filepath in glob(folder_path + "/*"):
        if re.search(r"\.[a-z]{10}$", filepath):
            os.rename(filepath, filepath[:-11])


def get_page_info_list(date_format: str, hide_scheduled_posts=True) -> Tuple[List[Dict], int]:
    local_time = localtime()
    print("Local time is {}".format(strftime('%Y-%m-%dT%H:%M:%SZ', local_time)))
    page_info_list = []
    scheduled_post_count = 0
    for page_path in glob("your_content/comics/*"):
        page_info = read_info("{}/info.ini".format(page_path), to_dict=True, might_be_scheduled=True)
        if strptime(page_info["Post date"], date_format) > local_time:
            scheduled_post_count += 1
            # Post date is in the future, so rename all resource files so they can't easily be found
            if hide_scheduled_posts:
                schedule_files(page_path)
        else:
            # Post date is in the past, so publish the comic files
            unschedule_files(page_path)
            page_info["page_name"] = os.path.basename(page_path)
            page_info["Tags"] = [tag.strip() for tag in page_info["Tags"].strip().split(",")]
            page_info_list.append(page_info)

    page_info_list = sorted(
        page_info_list,
        key=lambda x: (strptime(x["Post date"], date_format), x["page_name"])
    )
    return page_info_list, scheduled_post_count


def save_page_info_json_file(page_info_list: List, scheduled_post_count: int):
    d = {
        "page_info_list": page_info_list,
        "scheduled_post_count": scheduled_post_count
    }
    with open("comic/page_info_list.json", "w") as f:
        f.write(dumps(d))


def get_ids(comic_list: List[Dict], index):
    first_id = comic_list[0]["page_name"]
    last_id = comic_list[-1]["page_name"]
    return {
        "first_id": first_id,
        "previous_id": first_id if index == 0 else comic_list[index - 1]["page_name"],
        "current_id": comic_list[index]["page_name"],
        "next_id": last_id if index == (len(comic_list) - 1) else comic_list[index + 1]["page_name"],
        "last_id": last_id
    }


def create_comic_data(page_info: dict, first_id: str, previous_id: str, current_id: str, next_id: str, last_id: str):
    print("Building page {}...".format(page_info["page_name"]))
    with open("your_content/comics/{}/post.html".format(page_info["page_name"]), "rb") as f:
        post_html = f.read().decode("utf-8")
    return {
        "page_name": page_info["page_name"],
        "filename": page_info["Filename"],
        "comic_path": "your_content/comics/{}/{}".format(
            page_info["page_name"],
            page_info["Filename"]
        ),
        "thumbnail_path": "your_content/comics/{}/{}".format(
            page_info["page_name"],
            os.path.splitext(page_info["Filename"])[0] + "_thumbnail.jpg"
        ),
        "alt_text": html.escape(page_info["Alt text"]),
        "first_id": first_id,
        "previous_id": previous_id,
        "current_id": current_id,
        "next_id": next_id,
        "last_id": last_id,
        "page_title": page_info["Title"],
        "post_date": page_info["Post date"],
        "tags": page_info["Tags"],
        "post_html": post_html
    }


def build_comic_data_dicts(page_info_list: List[Dict]) -> List[Dict]:
    comic_data_dicts = []
    for i, page_info in enumerate(page_info_list):
        comic_dict = create_comic_data(page_info, **get_ids(page_info_list, i))
        comic_data_dicts.append(comic_dict)
    return comic_data_dicts


def resize(im, size):
    if "," in size:
        # Convert a string of the form "100, 36" into a 2-tuple of ints (100, 36)
        x, y = size.strip().split(",")
        new_size = (int(x.strip()), int(y.strip()))
    elif size.endswith("%"):
        # Convert a percentage (50%) into a new size (50, 18)
        size = float(size.strip().strip("%"))
        size = size / 100
        x, y = im.size
        new_size = (int(x * size), int(y * size))
    else:
        raise ValueError("Unknown resize value: {!r}".format(size))
    return im.resize(new_size)


def process_comic_image(comic_info, comic_page_path, create_thumbnails, create_low_quality):
    section = "Image Reprocessing"
    comic_page_dir = os.path.dirname(comic_page_path)
    comic_page_name, comic_page_ext = os.path.splitext(os.path.basename(comic_page_path))
    with open(comic_page_path, "rb") as f:
        im = Image.open(f)
        if create_thumbnails:
            thumb_im = resize(im, comic_info.get(section, "Thumbnail size"))
            thumb_im.save(os.path.join(comic_page_dir, comic_page_name + "_thumbnail.jpg"))
        if create_low_quality:
            file_type = comic_info.get(section, "Low-quality file type")
            im.save(os.path.join(comic_page_dir, comic_page_name + "_low_quality." + file_type.lower()))


def process_comic_images(comic_info, comic_data_dicts: List[Dict]):
    section = "Image Reprocessing"
    create_thumbnails = comic_info.getboolean(section, "Create thumbnails")
    create_low_quality = comic_info.getboolean(section, "Create low-quality versions of images")
    if create_thumbnails or create_low_quality:
        for comic_data in comic_data_dicts:
            process_comic_image(comic_info, comic_data["comic_path"][3:], create_thumbnails, create_low_quality)


def get_archive_sections(comic_info: RawConfigParser, comic_data_dicts: List[Dict]) -> List[Dict[str, List]]:
    archive_sections = []
    for section in comic_info.get("Archive", "Archive sections").strip().split(","):
        section = section.strip()
        pages = [comic_data for comic_data in comic_data_dicts
                 if section in comic_data["tags"]]
        archive_sections.append({
            "name": section,
            "pages": pages
        })
    return archive_sections


def write_to_template(template_path, html_path, data_dict=None):
    if data_dict is None:
        data_dict = {}
    try:
        template = JINJA_ENVIRONMENT.get_template(template_path)
    except TemplateNotFound:
        print("Template file {} not found".format(template_path))
    else:
        with open(html_path, "wb") as f:
            rendered_template = template.render(
                autogenerate_warning=AUTOGENERATE_WARNING,
                comic_title=COMIC_TITLE,
                base_dir=BASE_DIRECTORY,
                links=LINKS_LIST,
                **data_dict
            )
            f.write(bytes(rendered_template, "utf-8"))


def write_html_files(comic_info: RawConfigParser, comic_data_dicts: List[Dict]):
    # Write individual comic pages
    print("Writing {} comic pages...".format(len(comic_data_dicts)))
    for comic_data_dict in comic_data_dicts:
        html_path = "comic/{}.html".format(comic_data_dict["page_name"])
        write_to_template("comic.tpl", html_path, comic_data_dict)
    write_other_pages(comic_info, comic_data_dicts)


def write_other_pages(comic_info: RawConfigParser, comic_data_dicts: List[Dict]):
    archive_sections = get_archive_sections(comic_info, comic_data_dicts)
    last_comic_page = comic_data_dicts[-1]
    last_comic_page.update({
        "use_thumbnails": comic_info.getboolean("Archive", "Use thumbnails"),
        "archive_sections": archive_sections
    })
    pages_list = get_pages_list(comic_info)
    for page in pages_list:
        template_name = page["template_name"] + ".tpl"
        html_path = page["template_name"] + ".html"
        data_dict = {}
        data_dict.update(last_comic_page)
        if page["title"]:
            data_dict["page_title"] = page["title"]
        print("Writing {}...".format(html_path))
        write_to_template(template_name, html_path, data_dict)


def write_archive_page(comic_info: RawConfigParser, comic_data_dicts: List[Dict]):
    print("Building archive page...")
    archive_sections = get_archive_sections(comic_info, comic_data_dicts)
    write_to_template("archive.tpl", "archive.html", {
        "page_title": "Archive",
        "use_thumbnails": comic_info.getboolean("Archive", "Use thumbnails"),
        "archive_sections": archive_sections
    })


def write_tagged_page():
    print("Building tagged page...")
    write_to_template("tagged.tpl", "tagged.html", {"page_title": "Tagged posts"})


def write_infinite_scroll_page(comic_info: RawConfigParser, comic_data_dicts: List[Dict]):
    print("Building infinite scroll page...")
    archive_sections = get_archive_sections(comic_info, comic_data_dicts)
    write_to_template("infinite_scroll.tpl", "infinite_scroll.html", {
        "page_title": "Infinite scroll",
        "archive_sections": archive_sections
    })


def print_processing_times(processing_times: List[Tuple[str, float]]):
    last_processed_time = None
    print("")
    for name, t in processing_times:
        if last_processed_time is not None:
            print("{}: {:.2f} ms".format(name, (t - last_processed_time) * 1000))
        last_processed_time = t
    print("{}: {:.2f} ms".format("Total time", (processing_times[-1][1] - processing_times[0][1]) * 1000))


def main():
    global COMIC_TITLE, LINKS_LIST
    processing_times = [("Start", time())]

    # Get site-wide settings for this comic
    comic_info = read_info("your_content/comic_info.ini")
    COMIC_TITLE = comic_info.get("Comic Info", "Comic name")
    LINKS_LIST = get_links_list(comic_info)
    processing_times.append(("Get comic settings", time()))

    # Setup output file space
    setup_output_file_space(comic_info)
    processing_times.append(("Setup output file space", time()))

    # Get the info for all pages, sorted by Post Date
    page_info_list, scheduled_post_count = get_page_info_list(
        comic_info.get("Comic Settings", "Date format"),
        comic_info.getboolean("Comic Settings", "Hide scheduled posts")
    )
    print([p["page_name"] for p in page_info_list])
    processing_times.append(("Get info for all pages", time()))

    # Save page_info_list.json file for use by other pages
    save_page_info_json_file(page_info_list, scheduled_post_count)
    processing_times.append(("Save page_info_list.json file", time()))

    # Build full comic data dicts, to build templates with
    comic_data_dicts = build_comic_data_dicts(page_info_list)
    processing_times.append(("Build full comic data dicts", time()))

    # Create low-res and thumbnail versions of all the comic pages
    process_comic_images(comic_info, comic_data_dicts)
    processing_times.append(("Process comic images", time()))

    # Write page info to comic HTML pages
    write_html_files(comic_info, comic_data_dicts)
    processing_times.append(("Write HTML files", time()))

    # Build RSS feed
    build_rss_feed(comic_info, comic_data_dicts)
    processing_times.append(("Build RSS feed", time()))

    print_processing_times(processing_times)


if __name__ == "__main__":
    main()
