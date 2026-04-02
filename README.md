# pdf-notebooklm-cleaner

[![PyPI version](https://img.shields.io/pypi/v/pdf-notebooklm-cleaner)](https://pypi.org/project/pdf-notebooklm-cleaner/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/pdf-notebooklm-cleaner)](https://pypi.org/project/pdf-notebooklm-cleaner/)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/pdf-notebooklm-cleaner)](https://pypi.org/project/pdf-notebooklm-cleaner/)
[![License](https://img.shields.io/pypi/l/pdf-notebooklm-cleaner)](LICENSE)

命令行工具：输入 PDF，输出两类结果：
- 每页完整截图 ZIP
- 去除右下角 NotebookLM 标识后的 clean PDF

适合这类场景：PDF 每页内容完整、边框要保留、右下角有 NotebookLM logo/文字，需要批量清理后导出整页截图。

## 安装

```bash
pip install pdf-notebooklm-cleaner
```

## 用法

```bash
pdf-notebooklm-cleaner input.pdf
```

指定输出目录：

```bash
pdf-notebooklm-cleaner input.pdf -o ./out
```

提高渲染清晰度：

```bash
pdf-notebooklm-cleaner input.pdf --dpi 300
```

## 输出结构

默认会在输入 PDF 同目录下生成：

```text
<input_stem>_cleaned/
├── screenshots/
│   ├── page_01.png
│   ├── page_02.png
│   └── ...
├── <input_stem>_screenshots.zip
└── <input_stem>_clean.pdf
```

## 可调参数

- `--dpi`：渲染分辨率
- `--search-width-ratio`：右下角检测区域宽度比例
- `--search-height-ratio`：右下角检测区域高度比例
- `--dark-threshold`：检测暗色像素阈值
- `--bbox-pad-px`：检测框外扩像素
- `--edge-margin-px`：保留右/下边框的安全边距

## 工作原理

1. 用 PyMuPDF 将每页渲染为高分辨率 PNG
2. 在右下角区域自动检测 NotebookLM logo/文字位置
3. 以周边背景色覆盖该区域，尽量保留边框
4. 重新打包为截图 ZIP 和 clean PDF

## 局限

这个版本针对右下角 NotebookLM 标识的常见模板效果较好。若页面设计差异较大，建议优先调整：

- `--search-width-ratio`
- `--search-height-ratio`
- `--bbox-pad-px`
- `--edge-margin-px`

## 开发

```bash
python -m pip install -U build twine
python -m build
python -m twine check dist/*
```
