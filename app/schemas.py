from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


class TreeNode(BaseModel):
    name: str
    path: str
    type: Literal["file", "directory"]
    children: Optional[list[TreeNode]] = None


class FileContent(BaseModel):
    path: str
    name: str
    content: str
    language: str
    size: int


class CreateItemRequest(BaseModel):
    userId: str
    parentPath: str
    name: str
    type: Literal["file", "directory"]


class RenameItemRequest(BaseModel):
    userId: str
    path: str
    newName: str
