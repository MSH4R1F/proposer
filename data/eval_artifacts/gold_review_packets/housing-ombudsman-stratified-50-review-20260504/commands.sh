#!/usr/bin/env bash
set -euo pipefail

# Requires ANTHROPIC_API_KEY and OPENAI_API_KEY.
# Runs dual-provider pre-adjudication labeling; it does not append gold.

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202451564 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202451564.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202427949 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202427949.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202332678 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202332678.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202426484 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202426484.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202409223 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202409223.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202511615 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202511615.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202445527 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202445527.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202509252 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202509252.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202331162 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202331162.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202446687 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202446687.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202332724 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202332724.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202413497 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202413497.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202508313 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202508313.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202408056 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202408056.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202338295 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202338295.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202513245 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202513245.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202348669 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202348669.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202410423 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202410423.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202421521 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202421521.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202429736 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202429736.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202441018 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202441018.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202428538 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202428538.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202430026 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202430026.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202316658 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202316658.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-2022225 48 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-2022225 48.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202345261 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202345261.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202334994 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202334994.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202407044 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202407044.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202432454 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202432454.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202401431 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202401431.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202442504 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202442504.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202346688 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202346688.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202306436 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202306436.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202508050 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202508050.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202506211 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202506211.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202404949 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202404949.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202318374 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202318374.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202334890 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202334890.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202339075 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202339075.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202427803 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202427803.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202404522 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202404522.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202410679 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202410679.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202412991 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202412991.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202413845 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202413845.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202511313 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202511313.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202325309 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202325309.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202409957 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202409957.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202509792 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202509792.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202440462 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202440462.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a

venv/bin/python scripts/eval/auto_label.py \
  --case-id housing-ombudsman-202340236 \
  --pdf data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202340236.source_bundle.json \
  --domain-id housing.repairs_social.v1 \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --labeler-a anthropic:claude-sonnet-4-20250514 \
  --labeler-b openai:gpt-5.5 \
  --artifacts-root data/eval_artifacts/labeling \
  --gold-schema-hash 9c984b9a9289f6c23c3d183447593e5b552969de940528ab3db1f522a38d53f3 \
  --corpus-manifest-hash 67990fe4c2494566ab02686d2b22eb0d15d931afe83ac28c4b6268ade886673a
