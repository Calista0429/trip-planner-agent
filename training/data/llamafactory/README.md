# LLaMAFactory Data Entry

更新时间：2026-05-12

这个目录只保留 LLaMAFactory 的轻量入口和 manifest。大体积 train/val JSON/YAML 放在 `generated/`，默认由 `.gitignore` 排除。

## 目录

```text
training/data/llamafactory/
├── dataset_info.json     # 本地训练入口，file_name 指向 generated/
├── manifests/            # 可提交的小体积生成 manifest
├── generated/            # ignored，本地 train/val JSON/YAML
└── archive/              # ignored，历史导出
```

## 规则

- 新导出的 train/val JSON/YAML 默认写入 `generated/`。
- 需要公开记录的数据生成来源、样本数、混合比例和导出时间，写入 `manifests/`。
- 不要把大体积 train/val JSON/YAML 直接放回本目录根层。
