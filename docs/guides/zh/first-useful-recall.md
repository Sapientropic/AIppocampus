# 第一次有用召回

Role: 中文读者的 operational entry。

AIppocampus 的第一价值不是“模型自己记得”，而是后来的 agent 可以找到本地源线索，打开 source window，再谨慎继续。

## 新环境最小路径

```sh
git clone https://github.com/Sapientropic/AIppocampus.git
cd AIppocampus
python -m pip install -e ".[dev]"
aippocampus start --json
```

`start` 应该先指向首个可用召回路径，而不是让新用户先读完整 operator 诊断墙。

## 公共示例召回

```sh
aippocampus agent recall "can an agent catch up without pretending it has innate memory?" --cwd . --clean-source-dir ./examples/public-memory-bundle/clean-source --json
aippocampus agent deepen --request 1 --recall-selector <emitted-selector> --json
```

第一条命令只给 route。第二条命令打开 source。只有打开 source 后，agent 才可以在这个 scope 内使用更强的事实或原文判断。

## 什么时候用 search

如果你已经记得一段确切措辞，用 search 证明它存在：

```sh
aippocampus search "without pretending it has innate memory" --clean-source-dir ./examples/public-memory-bundle/clean-source --json
```

如果只有模糊线索，先用 `aippocampus agent recall`，再 `aippocampus agent deepen`。不要把 route 摘要当成 source 本身。

## 术语入口

中英术语对照见 [`docs/guides/glossary-bilingual.md`](../glossary-bilingual.md)。中文起源文的正本是 [`docs/未干的地图.md`](../../未干的地图.md)，英文版是 transcreation，不是替代正本。
