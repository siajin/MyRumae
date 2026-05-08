"""All UCLASS DOM selectors, grouped by page.

When LMS DOM changes, edit only this file. Selectors confirmed against the
HTML samples at the repo root (login / home / course / ubboard pages).
"""

BASE_URL = "https://uclass.uos.ac.kr"


class LOGIN:
    URL = f"{BASE_URL}/login/index.php"
    USERNAME = "input#input-username"
    PASSWORD = "input#input-password"
    SUBMIT = "button.btn-login"


class HOME:
    DASHBOARD_URL = f"{BASE_URL}/my/"
    LOGOUT_LINK = "a[href*='logout.php']"
    COURSE_ITEMS = "li.dropdown-item-course[data-courseid]"
    COURSE_LINK = "a.dropdown-item[href*='/course/view.php']"


class COURSE:
    URL_TMPL = f"{BASE_URL}/course/view.php?id={{cid}}"
    URL_FLAT = f"{BASE_URL}/course/view.php?id={{cid}}&mode=sections"

    SECTION = "li.section[data-sectionid], li.section[id^='section-']"
    SECTION_ID_ATTR = "data-sectionid"

    ACTIVITY = "li.activity.activity-wrapper[data-id]"
    ACTIVITY_ID_ATTR = "data-id"
    ACTIVITY_LINK = "a.activity-container"
    ACTIVITY_NAME = "div.activityname"

    PAGE_TITLE = "header h1, .page-header-headings h1"


class BOARD:
    URL_TMPL = f"{BASE_URL}/mod/ubboard/view.php?id={{cmid}}"
    ARTICLE_LINK = "a[href*='/mod/ubboard/article.php']"

    ARTICLE_TITLE = "h2.article-title, .article-header h2, h1"
    ARTICLE_AUTHOR = ".article-author, .author-name"
    ARTICLE_POSTED_AT = ".article-date, .posted-date"
    ARTICLE_BODY = ".article-content, .article-body, .ubboard-content"
    ARTICLE_ATTACH = "a[href*='/pluginfile.php']"


class FOLDER:
    URL_TMPL = f"{BASE_URL}/mod/folder/view.php?id={{cmid}}"
    FILE_LINK = "a[href*='/pluginfile.php']"
    DOWNLOAD_FOLDER_BTN = "button[name='downloadfolder'], a[href*='action=download']"


class ASSIGN:
    URL_TMPL = f"{BASE_URL}/mod/assign/view.php?id={{cmid}}"

    TITLE = ".page-header-headings h1, header h1"
    DUE_AT_ROW_LABEL = "td.cell.c0"
    DUE_AT_ROW_VALUE = "td.cell.c1"
    DESCRIPTION = "#intro, .activity-description, .no-overflow"
    ATTACH = "a[href*='/pluginfile.php']"
    SUBMITTED_FLAG = ".submissionstatussubmitted, .submitted"


def is_modtype(class_str: str, modtype: str) -> bool:
    if not class_str:
        return False
    return f"modtype_{modtype}" in class_str


KNOWN_MODTYPES = ("folder", "ubboard", "assign", "resource")
