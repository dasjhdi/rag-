"""运营侧接口（评估监控 / 模型统计）必须只对管理后台开放。

这两个页面原本挂在普通用户导航的「数据分析」下，任何人都能直接访问 URL。
收敛到管理后台后，后端必须逐条路由加门控，否则"隐藏入口"只是障眼法。

本测试不连数据库，只检查路由的依赖链是否带上了能力位。
"""

from app.api.v1.endpoints import evaluation, llm_stats


def route_capability(route) -> str | None:
    """Return the capability required by a route, if any."""
    for dependency in route.dependant.dependencies:
        capability = getattr(dependency.call, "capability", None)
        if capability:
            return capability
    return None


def test_every_evaluation_route_requires_a_capability():
    unguarded = [
        route.path
        for route in evaluation.router.routes
        if route_capability(route) is None
    ]
    assert unguarded == [], f"未加门控的评估接口：{unguarded}"


def test_every_llm_stats_route_requires_a_capability():
    unguarded = [
        route.path
        for route in llm_stats.router.routes
        if route_capability(route) is None
    ]
    assert unguarded == [], f"未加门控的统计接口：{unguarded}"


def test_aggregates_are_readable_by_viewer():
    """聚合指标对只读角色开放，否则后台看板对 viewer 全是 403。"""
    readable = {
        "/evaluation/statistics",
        "/evaluation/trends",
        "/evaluation/alerts",
        "/evaluation/health",
        "/llm-stats/summary",
        "/llm-stats/time-series",
        "/llm-stats/distribution/by-module",
        "/llm-stats/distribution/by-model",
        "/llm-stats/distribution/by-tool",
        "/llm-stats/time-series/tools",
        "/llm-stats/modules",
        "/llm-stats/models",
        "/llm-stats/tools",
    }
    for route in (*evaluation.router.routes, *llm_stats.router.routes):
        if route.path in readable:
            assert route_capability(route) == "read", route.path


def test_conversation_detail_requires_sessions_capability():
    """明细会暴露用户原文，只给「会话排障」能力，不给只读角色。"""
    detail_paths = {
        "/evaluation/conversation/{conversation_id}",
        "/evaluation/{evaluation_id}",
        "/llm-stats/conversation/{conversation_id}",
    }
    found = set()
    for route in (*evaluation.router.routes, *llm_stats.router.routes):
        if route.path in detail_paths:
            found.add(route.path)
            assert route_capability(route) == "sessions", route.path

    assert found == detail_paths
