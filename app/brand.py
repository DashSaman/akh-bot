"""Central brand configuration. PUBLIC brand != INTERNAL infrastructure name (akh-bot/akhbot).

All public surfaces (site, footer, OG, schema, RSS, telegram signature, emails) read from
this single source. Changing the brand later must only require editing config/brand.yml.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import yaml

DEFAULTS: dict[str, Any] = {
    "brand_status": "UNDECIDED",
    "name_fa": "اخ‌بات" ,  # placeholder preview name — NOT the final brand
    "name_en": "akh-bot preview",
    "short_name": "akh",
    "tagline_fa": "پیش‌نمایش سکوی خبری — نام نهایی هنوز انتخاب نشده است",
    "tagline_en": "Newsroom platform preview — final brand not selected yet",
    "logo": "/static/logo-placeholder.svg",
    "favicon": "/static/favicon.svg",
    "primary_domain": "",
    "organization_url": "",
    "telegram_handle": "",
    "x_handle": "",
    "instagram_handle": "",
    "threads_handle": "",
    "facebook_handle": "",
    "youtube_handle": "",
    "contact_email": "",
    "same_as": [],
    "publisher_type": "NewsMediaOrganization",
    "editorial_attribution_fa": "تحریریه خودکار مبتنی بر شواهد",
    "editorial_attribution_en": "Automated evidence-based editorial desk",
}


@dataclass
class Brand:
    data: dict[str, Any] = field(default_factory=lambda: dict(DEFAULTS))

    def __getattr__(self, key: str) -> Any:
        try:
            return self.data[key]
        except KeyError as e:  # pragma: no cover
            raise AttributeError(key) from e

    @property
    def decided(self) -> bool:
        return self.data.get("brand_status") == "DECIDED"

    def same_as_list(self, public_base_url: str = "") -> list[str]:
        out = list(self.data.get("same_as") or [])
        handles = {
            "telegram": f"https://t.me/{self.data.get('telegram_handle')}" if self.data.get("telegram_handle") else "",
            "x": f"https://x.com/{self.data.get('x_handle')}" if self.data.get("x_handle") else "",
            "instagram": f"https://instagram.com/{self.data.get('instagram_handle')}" if self.data.get("instagram_handle") else "",
            "threads": f"https://threads.net/@{self.data.get('threads_handle')}" if self.data.get("threads_handle") else "",
        }
        out += [u for u in handles.values() if u]
        if public_base_url:
            out.append(public_base_url.rstrip("/"))
        return list(dict.fromkeys(out))


def load_brand(path: str) -> Brand:
    data = dict(DEFAULTS)
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
        for k in DEFAULTS:
            if k in loaded and loaded[k] is not None:
                data[k] = loaded[k]
    return Brand(data)
