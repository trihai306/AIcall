Write-Output "=== GPU: bo nho va muc dung hien tai ==="
nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu,clocks.sm,clocks.max.sm,power.draw,power.limit --format=csv

Write-Output ""
Write-Output "=== Tien trinh dang chiem GPU ==="
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv

Write-Output ""
Write-Output "=== Triton co san khong (can cho torch.compile tren Windows) ==="
Set-Location C:\duan\chat-ai
.\.venv\python.exe -c "
import importlib.util as u, torch
print('  torch          ', torch.__version__)
print('  cuda           ', torch.version.cuda)
for m in ('triton','triton_windows'):
    s = u.find_spec(m)
    print(f'  {m:<15}', 'CO' if s else 'KHONG')
print('  sdpa flash     ', torch.backends.cuda.flash_sdp_enabled())
print('  sdpa mem_eff   ', torch.backends.cuda.mem_efficient_sdp_enabled())
print('  tf32 matmul    ', torch.backends.cuda.matmul.allow_tf32)
print('  cudnn tf32     ', torch.backends.cudnn.allow_tf32)
"
