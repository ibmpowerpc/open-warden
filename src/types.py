from typing import TypedDict


class PullRequestFile(TypedDict, total=False):
    path: str


class PullRequestData(TypedDict):
    number: int
    title: str
    body: str
    baseRefName: str
    headRefName: str
    headRefOid: str
    files: list[PullRequestFile]


class ReviewToolError(RuntimeError):
    pass
