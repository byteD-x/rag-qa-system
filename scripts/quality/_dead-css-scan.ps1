# 一次性分析脚本（审计用，只读）：统计全局 CSS 中「所有类名在 .vue 模板/脚本里都找不到」的规则
# 输出：每个文件的死规则行区间 + 总行数 + keyframes 引用情况
$ErrorActionPreference = 'Stop'
$root = (Get-Location).Path
$cssFiles = @(
  'apps/web/src/style.css',
  'apps/web/src/styles/theme-extras.css',
  'apps/web/src/styles/responsive-enhancements.css'
)

# --- 1. 收集「使用中」的类名：来自 .vue 的 <template> 与 <script>，以及 .ts ---
$vueFiles = Get-ChildItem -Recurse -File apps/web/src -Include *.vue | Where-Object { $_.Name -notmatch '\.test\.' }
$tsFiles  = Get-ChildItem -Recurse -File apps/web/src -Include *.ts  | Where-Object { $_.Name -notmatch '\.test\.' }
$usedText = New-Object System.Text.StringBuilder
foreach ($f in $vueFiles) {
  $t = Get-Content $f.FullName -Raw
  $m = [regex]::Match($t, '(?s)<template>(.*)</template>')
  if ($m.Success) { [void]$usedText.AppendLine($m.Groups[1].Value) }
  foreach ($s in [regex]::Matches($t, '(?s)<script[^>]*>(.*?)</script>')) { [void]$usedText.AppendLine($s.Groups[1].Value) }
}
foreach ($f in $tsFiles) { [void]$usedText.AppendLine((Get-Content $f.FullName -Raw)) }
$used = $usedText.ToString()

# Element Plus 类：按「该组件是否在模板中出现」判定
$liveEl = @(
  'el-alert','el-avatar','el-button','el-card','el-checkbox','el-checkbox-group','el-collapse','el-collapse-item',
  'el-config-provider','el-date-picker','el-date-editor','el-descriptions','el-descriptions-item','el-dialog',
  'el-divider','el-drawer','el-dropdown','el-dropdown-item','el-dropdown-menu','el-form','el-form-item','el-icon',
  'el-input','el-input-number','el-option','el-pagination','el-popover','el-popper','el-progress','el-radio',
  'el-radio-button','el-radio-group','el-select','el-skeleton','el-slider','el-switch','el-table','el-table-column',
  'el-tab-pane','el-tabs','el-tag','el-timeline','el-timeline-item','el-tooltip','el-message','el-message-box',
  'el-overlay','el-scrollbar','el-select-dropdown','el-textarea','el-loading','el-checkbox-button','el-switch-core'
)
# 已知死掉的 Element Plus 家族（其组件在模板中零出现）
$deadEl = @('el-menu','el-menu-item','el-upload','el-empty','el-link','el-container','el-aside','el-main','el-loading-mask','el-loading-spinner','el-upload-dragger','el-upload-list','el-icon-document','el-icon-picture-outline','el-icon-video-camera','el-icon-headset','el-icon-close','el-video-player','el-audio-player')

function Class-Tokens($sel) {
  @([regex]::Matches($sel, '\.([A-Za-z_][A-Za-z0-9_-]*)') | ForEach-Object { $_.Groups[1].Value })
}

# Vue 在运行时生成的过渡类：<transition name="X"> -> X-enter-active / X-leave-to ...
$transitionNames = @()
foreach ($f in $vueFiles) {
  foreach ($m in [regex]::Matches((Get-Content $f.FullName -Raw), '<transition\s+name="([A-Za-z0-9-]+)"')) {
    $transitionNames += $m.Groups[1].Value
  }
}
$transitionNames = $transitionNames | Sort-Object -Unique

# Element Plus 运行时生成的状态类：组件活着这些就是活的
$liveStateClasses = @(
  'is-plain','is-focus','is-focused','is-active','is-disabled','is-success','is-exception','is-loading',
  'is-round','is-circle','is-text','is-link','is-current','is-checked','is-indeterminate','is-finished',
  'is-hovering','is-narrow','is-selected','is-highlighted','is-opened','is-dragging','is-empty','is-vertical'
)

$report = @()
foreach ($rel in $cssFiles) {
  $abs = Join-Path $root $rel
  $text = Get-Content $abs -Raw
  # 注释替换为等量换行，保持行号
  $text = [regex]::Replace($text, '(?s)/\*.*?\*/', { param($m) ($m.Value -replace '[^\n]', '') })
  $chars = $text.ToCharArray()
  $line = 1
  $buf = New-Object System.Text.StringBuilder
  $stack = New-Object System.Collections.Stack
  $rules = @()
  $curStart = 1
  for ($i = 0; $i -lt $chars.Length; $i++) {
    $c = $chars[$i]
    if ($c -eq "`n") { $line++ }
    if (-not [char]::IsWhiteSpace($c) -and $buf.ToString().Trim().Length -eq 0) { $curStart = $line }
    if ($c -eq '{') {
      $sel = $buf.ToString().Trim()
      $buf.Clear() | Out-Null
      $stack.Push(@{ sel = $sel; start = $curStart; line = $line })
      if ($sel -like '@*') {
        # at-rule：@media / @keyframes 等，作为容器，不单独判定
        $curStart = $line + 1
      }
      continue
    }
    if ($c -eq '}') {
      if ($stack.Count -gt 0) {
        $ctx = $stack.Pop()
        $rules += [pscustomobject]@{ Selector = $ctx.sel; Start = $ctx.start; End = $line; Depth = $stack.Count }
      }
      $buf.Clear() | Out-Null
      $curStart = $line + 1
      continue
    }
    [void]$buf.Append($c)
  }

  foreach ($r in $rules) {
    $sel = $r.Selector
    if ([string]::IsNullOrWhiteSpace($sel)) { continue }
    if ($sel -like '@*') { continue }
    if ($sel -match '^\s*[\d.]+%?\s*(,|$)') { continue }   # keyframes 内部帧
    if ($sel -eq 'from' -or $sel -eq 'to') { continue }
    if ($sel -match '^(:root|\*|html|body|#app|a|p|img|h[1-6]|button|::|-webkit|input|textarea|select|ul|ol|li|table|code|pre|blockquote)\b') { continue }
    $tokens = Class-Tokens $sel
    if ($tokens.Count -eq 0) { continue }
    # Vue 过渡类：只有精确的 enter/leave 后缀才算，禁止前缀匹配（否则 .page-hero 会被 "page" 吞掉）
    $transitionSuffixes = @('-enter-active','-leave-active','-enter-from','-leave-to','-enter-to','-leave-from','-enter','-leave','-move')
    $isTransitionClass = $false
    foreach ($tn in $transitionNames) {
      foreach ($sfx in $transitionSuffixes) {
        if ($tokens -contains ($tn + $sfx)) { $isTransitionClass = $true }
      }
    }
    if ($isTransitionClass) { continue }
    $projTokens = @($tokens | Where-Object { -not $_.StartsWith('el-') -and $liveStateClasses -notcontains $_ })
    $elTokens   = @($tokens | Where-Object { $_.StartsWith('el-') })
    $verdict = $null
    if ($projTokens.Count -gt 0) {
      $anyUsed = $false
      foreach ($t in $projTokens) { if ($used -cmatch ('(?<![A-Za-z0-9_-])' + [regex]::Escape($t) + '(?![A-Za-z0-9_-])')) { $anyUsed = $true; break } }
      if (-not $anyUsed) { $verdict = 'dead' }
    } elseif ($elTokens.Count -gt 0) {
      # 纯 Element Plus 选择器：只有在整个家族都死的时候才算死
      $family = $elTokens | Where-Object { $deadEl -contains $_ }
      $liveFam = $elTokens | Where-Object { $liveEl -contains $_ }
      if ($family.Count -gt 0 -and $liveFam.Count -eq 0) { $verdict = 'dead-el' }
    }
    if ($verdict) {
      $report += [pscustomobject]@{ File = $rel.Replace('apps/web/src/', ''); Lines = ($r.End - $r.Start + 1); Range = "$($r.Start)-$($r.End)"; Kind = $verdict; Selector = ($sel -replace '\s+', ' ') }
    }
  }
}

$out = Join-Path $root 'scripts/quality/_dead-css-report.json'
$report | Sort-Object File, { [int](($_.Range -split '-')[0]) } | ConvertTo-Json -Depth 4 | Set-Content -Path $out -Encoding utf8
"===== 汇总 ====="
$report | Group-Object File | ForEach-Object { "{0,-38} 规则数 {1,3}  行数 {2,4}" -f $_.Name, $_.Count, (($_.Group | Measure-Object Lines -Sum).Sum) }
"总计死规则 {0} 条，合计 {1} 行" -f $report.Count, (($report | Measure-Object Lines -Sum).Sum)
"JSON -> $out"
