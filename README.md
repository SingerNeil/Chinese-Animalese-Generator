# Chinese Animalese Generator

一个在本机运行的中文动森语音生成器。输入中文文本，即可生成轻快、
角色化的拟声 WAV 音频，并在网页中试听、查看波形和下载。

> 这不是 AI 文字转语音，也不会合成清晰可懂的真人语音。它通过中文拼音
> 拆分与短音频拼接，生成适合配合字幕使用的 Animalese 风格拟声。

## 功能

- 中文文本转 Animalese 风格 WAV 音频
- 四档角色音色
- 独立调节语速、音高、音调起伏和标点停顿
- 三种齿音/气声处理方式
- 确定性生成与自定义变化编号
- 浏览器内即时试听、波形预览和下载
- 完全在本机处理，不上传文案或音频

## 声音引擎

- `equalo`：将中文声母、韵母映射到四套角色声音，并加入随机音高变化和
  普通话声调轮廓。默认使用这个引擎。
- `mandarin`：使用 `KoSukeWork/Animalese-Synthesizer` 的 57 个中文音素，
  再应用动态拼接处理。该引擎仍属于实验选项。

## Windows 安装

需要 Python 3.10 或更高版本。独立调节语速还需要安装 FFmpeg，并确保
终端中可以运行 `ffmpeg` 命令。

```powershell
git clone https://github.com/SingerNeil/Chinese-Animalese-Generator.git
cd Chinese-Animalese-Generator
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 启动网页

双击 `start.bat`，或在 PowerShell 中运行：

```powershell
.\start.bat
```

程序会打开 `http://127.0.0.1:7860`。关闭启动窗口即可停止服务。生成的文件
保存在 `output/web`，程序只保留最近 50 个 WAV 文件。

如需更改端口，可在启动前设置 `ANIMALESE_PORT` 环境变量。

## 命令行使用

```powershell
.\.venv\Scripts\python.exe .\chinese_animalese.py `
  "欢迎来到小岛，今天也要开心呀！" `
  --backend equalo `
  --voice med `
  --dehiss remap `
  --speed 1.0 `
  --pitch 0 `
  --out .\output\demo-equalo.wav
```

切换到中文音素声库：

```powershell
.\.venv\Scripts\python.exe .\chinese_animalese.py `
  "欢迎来到小岛，今天也要开心呀！" `
  --backend mandarin `
  --voice med `
  --out .\output\demo-mandarin.wav
```

默认变化编号由文本、声音引擎和音色共同决定，所以同一条命令会生成相同的
WAV。使用 `--seed` 可以主动尝试不同变化。

`equalo` 引擎支持三种齿音处理：

- `--dehiss off`：保留原始 `s`、`x`、`sh` 片段。
- `--dehiss filter`：保留这些片段，但增加低通滤波和边缘淡化。
- `--dehiss remap`：用更柔和的 `z`、`j`、`r` 片段替代，默认使用。

## 测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## 第三方素材与使用提醒

本项目包含来自两个开源项目的声音素材，详情和许可证副本见
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。其中 Equalo 仓库没有单独
说明 WAV 素材的原始来源与许可。将生成音频用于商业内容或再次分发前，请自行
核实素材权利，或替换为权利清晰的自有声库。

本项目与 Nintendo 或《Animal Crossing》没有隶属、授权或背书关系。
