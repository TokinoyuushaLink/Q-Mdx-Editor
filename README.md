# Q-Mdx-Editor
PyQT做的mdx编辑器
<img width="1502" height="939" alt="图片" src="https://github.com/user-attachments/assets/2c078b99-d49b-49aa-8afb-fe5b6866dc63" />
<img width="1500" height="937" alt="图片" src="https://github.com/user-attachments/assets/b66213e6-1dab-4213-8317-b8545f637eae" />

如果你也在为如何制作mdx而烦恼，不妨看看这个编辑器\
将词条写进SqLite，然后再发布为Mdx\
- 非chromium预览，保持简洁
- 支持Markdown/HTML混合语法
- 支持自定义css
- 支持自动HTML语法补全
- 附带各种常规设置
- 支持主题切换

### 编译
首先，你需要`uv`\
dev：
```
uv sync
.venv\scripts\activate
uv run main.py
```
Build Release:
```
uv sync
.venv\scripts\activate
uv run pyinstaller dict_editor.spec --clean -y
```
