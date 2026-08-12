import torch
print("torch:", torch.__version__)
print("cuda :", torch.version.cuda)
print("arch da bien dich:", torch.cuda.get_arch_list())
print("card :", torch.cuda.get_device_name(0), torch.cuda.get_device_capability(0))
