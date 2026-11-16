复现中期结果

Python 3.10或以上。进入本文件所在目录后运行：
python -m venv .venv

macOS/Linux 激活：source .venv/bin/activate
Windows 激活：.venv\Scripts\activate

python -m pip install -r requirements-midterm.txt
python scripts/build_midterm.py --output ../rebuilt
python scripts/validate_midterm.py --results ../rebuilt

输出目录须为空。安装依赖需联网；输入随包提供，计算不需联网。
数据和图形由同一Python模型生成，页面只选择已计算结果。
结果基于情景假设，不是历史政策因果识别。
