"""告警配置：阈值、通知渠道与冷却窗口。

对应 ``config.yml`` 的 ``alerts`` 段。没有配置 webhook 时，告警仍会落库
（后台可见），只是不对外发送，便于先观察阈值是否合适。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AlertThresholds:
    """触发阈值。比值类参数用「倍数」或「百分比」表达。"""

    # 今日成本相对过去 7 日均值的倍数（1.5 = 上涨 50%）
    cost_spike_ratio: float = 1.5
    # 成本绝对值下限（元），避免几毛钱的波动反复告警
    cost_min_amount: float = 5.0
    # LLM 调用错误率（0-1）
    error_rate: float = 0.05
    # 参与计算错误率的最小样本量，样本太少不告警
    error_min_samples: int = 50
    # RAGAS 评测失败率（0-1）
    eval_error_rate: float = 0.2
    # 评测最小样本量
    eval_min_samples: int = 10


@dataclass
class AlertsConfig:
    """告警总开关与调度参数。"""

    enabled: bool = True
    # 巡检间隔（秒）
    interval_seconds: int = 300
    # 同类告警的冷却时间（分钟），期间重复触发只落库不重复推送
    cooldown_minutes: int = 120
    # 通知渠道：none / webhook（企业微信机器人可直接填其 webhook 地址）
    channel: str = "none"
    webhook_url: str = ""
    # 通知标题前缀
    title_prefix: str = "[CookHero]"
    thresholds: AlertThresholds = field(default_factory=AlertThresholds)

    def should_notify(self) -> bool:
        return self.channel == "webhook" and bool(self.webhook_url.strip())


DefaultAlertsConfig = AlertsConfig()
