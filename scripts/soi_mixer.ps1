$S = "21f10e44220c7ece"
$M = "/data/local/tmp/mixctl"
# Doc CA HAI bo control: cua tuyen codec lan tuyen usb, de biet dang o tuyen nao.
$ten = @("ABOX UAIF0 SPK","AIF1TX1 Input 2","AIF1TX2 Input 2","ABOX SPUS OUT0",
         "ABOX NSRC1","ABOX SIFS2","ABOX ERAP info USB On")
$lenh = ($ten | ForEach-Object { "$M get `"$_`"" }) -join "; "
& adb -s $S shell "su -c '$lenh'" 2>&1
