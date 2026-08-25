from __future__ import annotations

from archaeology.classify.features import ChangeFeatures

SIGNIFICANT = "significant"
INSIGNIFICANT_WHITESPACE = "insignificant_whitespace"
INSIGNIFICANT_COMMENT = "insignificant_comment"
INSIGNIFICANT_FORMAT = "insignificant_format"

RULE_VERSION_FLOOR_V1 = "floor.v1"
RULE_VERSION_AST_JS_V1 = "floor.v1+ast-js.v1"


def label_from_features(features: ChangeFeatures) -> str:
    """Pure function over cached features; floor rules only, recall-biased."""
    if features.pure_rename:
        return SIGNIFICANT
    if features.whitespace_only:
        return INSIGNIFICANT_WHITESPACE
    if features.comment_only:
        return INSIGNIFICANT_COMMENT
    return SIGNIFICANT


def label_from_features_v2(features: ChangeFeatures, ast_format_only: bool | None) -> str:
    """Layered rule: floor first; AST layer only upgrades otherwise-significant commits."""
    floor_label = label_from_features(features)
    if floor_label == SIGNIFICANT and ast_format_only:
        return INSIGNIFICANT_FORMAT
    return floor_label
