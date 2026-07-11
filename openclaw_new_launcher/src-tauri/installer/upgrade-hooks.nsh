; Lossless update guard. This file only preserves data when the application
; update handoff created update-pending.json. A normal uninstall keeps the
; standard Tauri delete-data behavior.

!macro NSIS_HOOK_PREINSTALL
  ; Historical installers used Chinese and short LOOM registry identities.
  ; Their stale uninstall entries are removed only when they point at the same
  ; directory selected for this installation.
  ReadRegStr $R8 HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\麓鸣AI矩阵获客工作台" "InstallLocation"
  StrCmp $R8 "$INSTDIR" 0 +2
    DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\麓鸣AI矩阵获客工作台"
  ReadRegStr $R8 HKCU "Software\LOOM" "InstallLocation"
  StrCmp $R8 "$INSTDIR" 0 +2
    DeleteRegKey HKCU "Software\LOOM"
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  IfFileExists "$LOCALAPPDATA\LOOM\update-pending.json" 0 loom_no_update_preserve
  IfFileExists "$INSTDIR\data\*.*" 0 loom_no_update_preserve
  CreateDirectory "$LOCALAPPDATA\LOOM\upgrade-staging\data"
  nsExec::ExecToLog '"$SYSDIR\robocopy.exe" "$INSTDIR\data" "$LOCALAPPDATA\LOOM\upgrade-staging\data" /E /COPY:DAT /DCOPY:DAT /R:2 /W:1 /NFL /NDL /NJH /NJS'
  loom_no_update_preserve:
!macroend

!macro NSIS_HOOK_POSTINSTALL
  IfFileExists "$LOCALAPPDATA\LOOM\update-pending.json" 0 loom_no_update_restore
  IfFileExists "$LOCALAPPDATA\LOOM\upgrade-staging\data\*.*" 0 loom_no_update_restore
  CreateDirectory "$INSTDIR\data"
  nsExec::ExecToLog '"$SYSDIR\robocopy.exe" "$LOCALAPPDATA\LOOM\upgrade-staging\data" "$INSTDIR\data" /E /COPY:DAT /DCOPY:DAT /R:2 /W:1 /NFL /NDL /NJH /NJS'
  RMDir /r "$LOCALAPPDATA\LOOM\upgrade-staging"
  loom_no_update_restore:
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
  ; Recovery is completed by the detached update handoff after setup exits.
!macroend
