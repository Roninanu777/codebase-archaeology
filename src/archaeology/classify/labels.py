from __future__ import annotations

from archaeology.classify.features import ChangeFeatures

SIGNIFICANT = "significant"
INSIGNIFICANT_WHITESPACE = "insignificant_whitespace"
INSIGNIFICANT_COMMENT = "insignificant_comment"

RULE_VERSION_FLOOR_V1 = "floor.v1"


def label_from_features(features: ChangeFeatures) -> str:
    """Pure function over cached features; floor rules only, recall-biased."""
    if features.pure_rename:
        return SIGNIFICANT
    if features.whitespace_only:
        return INSIGNIFICANT_WHITESPACE
    if features.comment_only:
        return INSIGNIFICANT_COMMENT
    return SIGNIFICANT
