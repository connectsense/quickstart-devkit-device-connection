# This repository is part of the Quick Start Devkit Project
Use this script to connect your phisical device to the Cloud, after deploying your infrastructure

## Connecting Your ConnectSense Device and Pushing Data

1. Go to `device-connection` folder (this project uses python3.8)
2. Install the dependencies
3. Fill the `conf-staging-example.txt` file with the data of your environment. You can find the `iotURL` with the command:
```bash
aws iot describe-endpoint --endpoint-type iot:Data-ATS
```
4. Connect the device that will run this script to the SoftAP of the device
5. Run the python script. `$ python cs-cord-dk-prov.py -h` will show the help section
6. `$ python cs-cord-dk-prov.py conf conf-staging-example.txt` will register your device in your AWS environment