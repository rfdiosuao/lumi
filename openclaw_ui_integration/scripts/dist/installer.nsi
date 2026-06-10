; Per-user desktop installer for OpenClaw, Modern UI 2 + Simplified Chinese.
; Lays the thin-portable payload (OpenClaw.exe + OpenClawFiles skeleton) into
; %LOCALAPPDATA%\OpenClaw (writable, no admin), makes shortcuts, and registers
; an uninstaller. First run downloads the runtime layers next to it; re-running
; the setup overwrites the launcher but keeps the layers (the self-update path).
;
; Defines from build-installer.ps1 via makensis /D:
;   PAYLOAD_DIR, OUTFILE, APPVERSION, ART_DIR, ICON

Unicode true
!include "MUI2.nsh"

!ifndef APP
  !define APP "OpenClaw"
!endif
!ifndef PAYLOAD_DIR
  !define PAYLOAD_DIR "payload"
!endif
!ifndef OUTFILE
  !define OUTFILE "OpenClaw-Setup.exe"
!endif
!ifndef APPVERSION
  !define APPVERSION "2.0.6"
!endif
!ifndef ART_DIR
  !define ART_DIR "assets"
!endif

!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP}"

Name "${APP} ${APPVERSION}"
OutFile "${OUTFILE}"
RequestExecutionLevel user
InstallDir "$LOCALAPPDATA\${APP}"
InstallDirRegKey HKCU "Software\${APP}" "InstallDir"
SetCompressor /SOLID lzma
BrandingText "${APP} ${APPVERSION}"

; --- Modern UI theming ---
!ifdef ICON
  !define MUI_ICON "${ICON}"
  !define MUI_UNICON "${ICON}"
!endif
!define MUI_WELCOMEFINISHPAGE_BITMAP "${ART_DIR}\welcome.bmp"
!define MUI_UNWELCOMEFINISHPAGE_BITMAP "${ART_DIR}\welcome.bmp"
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_BITMAP "${ART_DIR}\header.bmp"
!define MUI_HEADERIMAGE_RIGHT
!define MUI_ABORTWARNING

!define MUI_WELCOMEPAGE_TITLE "欢迎安装 ${APP}"
!define MUI_WELCOMEPAGE_TEXT "即将把 ${APP} ${APPVERSION} 安装到你的电脑（无需管理员权限）。$\r$\n$\r$\n首次启动会自动下载运行组件，请保持联网。$\r$\n$\r$\n点击「下一步」继续。"
!define MUI_DIRECTORYPAGE_TEXT_TOP "选择安装位置（默认安装到当前用户目录，免管理员）。"
!define MUI_FINISHPAGE_RUN "$INSTDIR\OpenClaw.exe"
!define MUI_FINISHPAGE_RUN_TEXT "立即启动 ${APP}"
!define MUI_FINISHPAGE_TEXT "${APP} 已安装完成。首次启动会下载运行组件，请保持联网。"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "SimpChinese"

Section "Install"
  ; Stop a running instance so files can be overwritten (self-update case).
  ExecWait 'taskkill /IM OpenClaw.exe /F' $0
  SetOutPath "$INSTDIR"
  File /r "${PAYLOAD_DIR}\*.*"

  CreateShortCut "$DESKTOP\${APP}.lnk" "$INSTDIR\OpenClaw.exe" "" "$INSTDIR\OpenClaw.exe" 0
  CreateDirectory "$SMPROGRAMS\${APP}"
  CreateShortCut "$SMPROGRAMS\${APP}\${APP}.lnk" "$INSTDIR\OpenClaw.exe" "" "$INSTDIR\OpenClaw.exe" 0
  CreateShortCut "$SMPROGRAMS\${APP}\Uninstall ${APP}.lnk" "$INSTDIR\Uninstall.exe"

  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "Software\${APP}" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayName" "${APP}"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayVersion" "${APPVERSION}"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayIcon" "$INSTDIR\OpenClaw.exe"
  WriteRegStr HKCU "${UNINST_KEY}" "UninstallString" "$\"$INSTDIR\Uninstall.exe$\""
  WriteRegStr HKCU "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINST_KEY}" "Publisher" "${APP}"
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoRepair" 1
SectionEnd

Section "Uninstall"
  ExecWait 'taskkill /IM OpenClaw.exe /F' $0
  Delete "$DESKTOP\${APP}.lnk"
  RMDir /r "$SMPROGRAMS\${APP}"
  RMDir /r "$INSTDIR"
  DeleteRegKey HKCU "${UNINST_KEY}"
  DeleteRegKey HKCU "Software\${APP}"
SectionEnd
