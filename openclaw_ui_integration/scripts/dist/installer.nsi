; Per-user desktop installer for OpenClaw. Lays the thin-portable payload
; (OpenClaw.exe + OpenClawFiles skeleton) into %LOCALAPPDATA%\OpenClaw, a
; writable no-admin location, so the first-run bootstrap can download the
; runtime layers next to it (the proven portable layout). Re-running the setup
; overwrites the launcher but leaves the downloaded layers in place, which is
; also how a launcher self-update applies.
;
; Defines come from build-installer.ps1 via makensis /D flags:
;   PAYLOAD_DIR, OUTFILE, APPVERSION

Unicode true
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

!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP}"

Name "${APP} ${APPVERSION}"
OutFile "${OUTFILE}"
RequestExecutionLevel user
InstallDir "$LOCALAPPDATA\${APP}"
InstallDirRegKey HKCU "Software\${APP}" "InstallDir"
SetCompressor /SOLID lzma
ShowInstDetails show
BrandingText "${APP} ${APPVERSION}"

Page directory
Page instfiles
UninstPage uninstConfirm
UninstPage instfiles

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
