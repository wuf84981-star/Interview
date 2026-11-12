"""search：本地 mock 知识库检索（不依赖任何外部服务）。

打分方式：把查询切成 2-gram，统计每篇文档的词频命中数。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.tools.registry import Tool, registry


@dataclass(frozen=True)
class Doc:
    title: str
    content: str


DOCS: list[Doc] = [
    Doc("远程办公管理规定", "员工每周可申请不超过两天远程办公，需提前一天在系统提交申请，由直属主管审批。"),
    Doc("差旅报销流程", "出差前在系统提交行程单，差旅结束后十个工作日内上传发票与行程记录，财务审核后次月打款。"),
    Doc("年假与调休制度", "入职满一年享有五天年假，满三年十天。年假需提前三个工作日申请，当年未休完可顺延至次年三月。"),
    Doc("技术栈说明", "前端使用 Vue3 与 Vite，后端使用 FastAPI，数据库为 PostgreSQL，部署在容器平台。"),
    Doc("接口联调规范", "所有接口以 /api 为前缀，统一返回 JSON，错误响应包含 message 字段，禁止在响应中返回堆栈信息。"),
    Doc("代码评审标准", "每个变更至少一人评审，评审关注边界条件、异常处理与测试覆盖，合并前必须通过 CI。"),
    Doc("周报提交要求", "每周五十七点前提交周报，内容包含本周进展、下周计划与风险项，字数不少于两百字。"),
    Doc("信息安全红线", "禁止将生产环境密钥写入代码仓库，禁止在公开文档中记录账号密码，敏感数据导出需审批。"),
    Doc("新员工入职清单", "入职当天领取设备并开通账号，三天内完成安全培训，一周内与主管确认试用期目标。"),
    Doc("会议管理约定", "会议需提前预约会议室并写明议程，超过三十分钟的会议必须有结论与责任人。"),
]


def _bigrams(text: str) -> list[str]:
    cleaned = re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]", "", text)
    if len(cleaned) < 2:
        return [cleaned] if cleaned else []
    return [cleaned[i : i + 2] for i in range(len(cleaned) - 1)]


def search_docs(session, args: dict) -> dict:
    query = str(args["query"]).strip()
    top_k = int(args.get("top_k", 3))
    if top_k < 1:
        top_k = 1
    terms = _bigrams(query)

    scored: list[tuple[float, Doc]] = []
    for doc in DOCS:
        haystack = doc.title + doc.content
        score = sum(haystack.count(term) for term in terms if term)
        if query and query in haystack:
            score += 5  # 整串命中的额外加权
        if score > 0:
            scored.append((float(score), doc))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    results = [
        {"title": doc.title, "snippet": doc.content[:80], "score": score}
        for score, doc in scored[:top_k]
    ]
    return {"query": query, "count": len(results), "results": results}


registry.register(
    Tool(
        name="search",
        description="在本地知识库中检索资料（模拟搜索引擎），返回标题与摘要。",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "检索关键词"},
                "top_k": {"type": "integer", "description": "返回条数，默认 3"},
            },
            "required": ["query"],
        },
        handler=search_docs,
    )
)
