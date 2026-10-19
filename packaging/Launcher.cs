// Original FMER Windows portable launcher. No installation or elevation.
using System;
using System.IO;
using System.Diagnostics;
using System.Windows.Forms;
class Launcher {
 [STAThread] static int Main(string[] args) {
  try {
   string root=AppDomain.CurrentDomain.BaseDirectory;
   string script=Path.Combine(root,"tools","portable_companion.py");
   var p=new ProcessStartInfo(Path.Combine(root,"runtime","pythonw.exe"),"-B \""+script+"\""+(Array.IndexOf(args,"--no-browser")>=0?" --no-browser":""));
   p.UseShellExecute=false;p.CreateNoWindow=true;p.WindowStyle=ProcessWindowStyle.Hidden;p.WorkingDirectory=root;
   using(var child=Process.Start(p)){child.WaitForExit();return child.ExitCode;}
  }catch(Exception e){MessageBox.Show(e.Message,"FMER could not start");return 1;}
 }
}
