# xrk
Python [AiM](https://www.aim-sportline.com) XRK file reader.

Once upon a time, AiM released a DLL to read their proprietary data file format
and provided some sample code for import into Matlab. That article can be found
[here](https://www.aim-sportline.com/download/software/doc/how-to-access-xrk-files-data-without-aim-software_101.pdf)

I don't use Matlab, but I can slap together Python, so here we are. This
repository contains a Python wrapper for the AiM provided DLL.

## Examples
Check out [examples.ipynb](examples.ipynb) in your browser or spin it up on
your computer in Jupyter notebook.

## Ideas for fun stuff to do
* Speed and friction traces, dig around in the data
* CSV exporter?
* Write some tests for each session? I may write an agent that looks for
  imported log files and makes sure I'm aware of values above/below a
  threshhold. Oil pressure too low? Colant temperature too high? I don't check
  that stuff every session, but I probably should...

