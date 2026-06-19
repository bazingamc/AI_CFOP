; AI_CFOP 安装脚本 - Inno Setup
; 使用方法: 在 Inno Setup 中编译此文件，或通过 build_exe.py --installer 自动构建
;
; 功能:
;   - 首次安装: 选择安装目录，完整安装
;   - 覆盖安装: 自动检测已安装目录，仅更新程序文件，保留所有本地数据

#define MyAppName "AI_CFOP"
#define MyAppVersion "1.4.0"
#define MyAppPublisher "AI_CFOP"
#define MyAppExeName "AI_CFOP.exe"
#define MyAppIcon "cube_ai_icon.ico"

[Setup]
; 应用唯一标识，用于注册表中识别已安装的应用
AppId={{B7E3F2A1-4D5C-6E8F-9A0B-1C2D3E4F5A6B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
; 输出目录
OutputDir=installer_output
OutputBaseFilename=AI_CFOP_Setup_{#MyAppVersion}
SetupIconFile={#MyAppIcon}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
; 允许在已安装时自动找到旧目录
UsePreviousAppDir=yes
; 不创建卸载快捷方式（保留数据）
UninstallDisplayName={#MyAppName}
; 卸载时不删除用户数据目录和文件
UninstallFilesDir={app}\uninstall

[Languages]
Name: "chinese"; MessagesFile: "compiler:Default.isl"

[Messages]
; 自定义中文界面文本
SetupAppTitle=安装 - {#MyAppName}
SetupWindowTitle=安装 - {#MyAppName}
WelcomeLabel1=欢迎使用 [name] 安装向导
WelcomeLabel2=此向导将引导您完成 [name/ver] 的安装。%n%n建议在继续之前关闭所有其他应用程序。
SelectDirLabel3=安装程序将把 [name] 安装到以下文件夹。
SelectDirBrowseLabel=如需安装到其他位置，请点击"浏览"。
DiskSpaceGBLabel=所需空间至少 [gb] GB。
SelectProgramGroupLabel=安装程序将在以下开始菜单文件夹中创建快捷方式。
SelectStartMenuFolderBrowseLabel=如需选择其他文件夹，请点击"浏览"。
ReadyLabel1=安装程序已准备好将 [name] 安装到您的计算机。
ReadyLabel2a=点击"安装"开始安装，或点击"上一步"修改设置。
InstallingLabel=正在安装，请稍候...
FinishedHeadingLabel=[name] 安装完成
FinishedLabelNoIcons=[name] 已成功安装到您的计算机。
FinishedLabel=[name] 已成功安装到您的计算机。
ClickFinish=点击"完成"退出安装向导。
UninstallAppTitle=卸载 - {#MyAppName}
UninstallAppFullTitle=卸载 - %1
ConfirmUninstall=确定要卸载 AI_CFOP 吗？%n%n您的个人数据（配置、记忆数据库、日志、分析结果）将被保留。%n%n如需彻底删除，请手动删除安装目录。
UninstallStatusLabel=正在卸载，请稍候...
UninstalledAll=[name] 已从您的计算机上卸载。%n%n个人数据文件已保留在安装目录中。
UninstalledMost=[name] 卸载完成。%n%n部分文件无法自动删除，您可以手动删除安装目录。
UninstalledAndNeedsRestart=[name] 卸载完成，但部分文件需要重启后删除。%n%n是否立即重启计算机？
ButtonInstall=安装(&I)
ButtonNext=下一步(&N) >
ButtonBack=< 上一步(&B)
ButtonCancel=取消
ButtonFinish=完成(&F)
ButtonYes=是(&Y)
ButtonNo=否(&N)
ButtonBrowse=浏览(&R)...
ButtonWizardBrowse=浏览(&R)...
StatusLabel=正在解压文件...
StatusExtractFiles=正在解压: %1
StatusCreateIcons=正在创建快捷方式...
StatusCreateShortcut=正在创建快捷方式: %1
StatusRegisterFiles=正在注册文件...
StatusRegisterFile=正在注册: %1
ExitSetupTitle=退出安装
ExitSetupMessage=安装尚未完成。如果现在退出，程序将不会被安装。%n%n您可以稍后再次运行安装程序完成安装。%n%n确定要退出安装吗？

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加图标:"; Flags: unchecked

[Dirs]
; 确保这些目录存在，但不标记为 alwaysdelete（卸载时不会自动删除）
Name: "{app}\logs"; Flags: uninsneveruninstall
Name: "{app}\results"; Flags: uninsneveruninstall
Name: "{app}\png\avatars"; Flags: uninsneveruninstall

[Files]
; ═══ 程序文件 - 安装/更新时始终覆盖 ═══
Source: "dist\AI_CFOP\AI_CFOP.exe"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "dist\AI_CFOP\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs

; ═══ 资源文件 - 安装/更新时始终覆盖 ═══
Source: "dist\AI_CFOP\png\OLL\*"; DestDir: "{app}\png\OLL"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "dist\AI_CFOP\png\PLL\*"; DestDir: "{app}\png\PLL"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "dist\AI_CFOP\default_avatar.png"; DestDir: "{app}"; Flags: ignoreversion

; ═══ 用户数据文件 - 仅在首次安装时创建，已存在则不覆盖 ═══
Source: "dist\AI_CFOP\.cfop_config.json"; DestDir: "{app}"; Flags: onlyifdoesntexist skipifsourcedoesntexist
; 注意: .cfop_op_algo.json 如果用户已自定义，不应覆盖
Source: "dist\AI_CFOP\.cfop_op_algo.json"; DestDir: "{app}"; Flags: onlyifdoesntexist skipifsourcedoesntexist

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
function InitializeSetup: Boolean;
begin
  Result := True;
end;

function InitializeUninstall: Boolean;
begin
  Result := True;
end;
