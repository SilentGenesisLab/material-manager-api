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


class SaveContentRequest(BaseModel):
    userId: str
    path: str
    content: str


class GraphNode(BaseModel):
    id: str
    name: str
    type: str = "file"


class GraphEdge(BaseModel):
    source: str
    target: str


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class SetBaseUrlRequest(BaseModel):
    baseUrl: str


class BaseUrlResponse(BaseModel):
    baseUrl: str
