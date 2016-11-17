# Template for a IPCM configuration file
ipcmconf_base = {
    "configFileVersion": "1.4.1",
    "localConfiguration": {
        "installationPath": "%(installpath)s/bin",
        "libraryPath": "%(installpath)s/lib",
        "logPath": "%(varpath)s/var/log",
        "consoleSocket": "%(varpath)s/var/run/ipcm-console.sock",
        "pluginsPaths": [
                "%(installpath)s/lib/rinad/ipcp",
                "/lib/modules/4.1.33-irati/extra"
        ]
        },

    "ipcProcessesToCreate": [],
    "difConfigurations": [],
}


da_map_base = {
    "applicationToDIFMappings": [
        {
            "encodedAppName": "rina.apps.echotime.server-1--",
            "difName": "n.DIF"
        },
        {
            "encodedAppName": "traffic.generator.server-1--",
            "difName": "n.DIF"
        }
    ],
}


# Template for a normal DIF configuration file
normal_dif_base =  {
    "difType" : "normal-ipc",
    "dataTransferConstants" : {
        "addressLength" : 2,
        "cepIdLength" : 2,
        "lengthLength" : 2,
        "portIdLength" : 2,
        "qosIdLength" : 2,
        "rateLength" : 4,
        "frameLength" : 4,
        "sequenceNumberLength" : 4,
        "ctrlSequenceNumberLength" : 4,
        "maxPduSize" : 10000,
        "maxPduLifetime" : 60000
    },

    "qosCubes" : [ {
            "name" : "unreliablewithflowcontrol",
            "id" : 1,
            "partialDelivery" : False,
            "orderedDelivery" : True,
            "efcpPolicies" : {
                "dtpPolicySet" : {
                    "name" : "default",
                    "version" : "0"
                },
                "initialATimer" : 0,
                "dtcpPresent" : True,
                "dtcpConfiguration" : {
                    "dtcpPolicySet" : {
                        "name" : "default",
                        "version" : "0"
                    },
                    "rtxControl" : False,
                    "flowControl" : True,
                    "flowControlConfig" : {
                        "rateBased" : False,
                        "windowBased" : True,
                        "windowBasedConfig" : {
                            "maxClosedWindowQueueLength" : 10,
                            "initialCredit" : 200
                        }
                    }
                }
            }
        }, {
            "name" : "reliablewithflowcontrol",
            "id" : 2,
            "partialDelivery" : False,
            "orderedDelivery" : True,
            "maxAllowableGap": 0,
            "efcpPolicies" : {
                "dtpPolicySet" : {
                    "name" : "default",
                    "version" : "0"
                },
                "initialATimer" : 0,
                "dtcpPresent" : True,
                "dtcpConfiguration" : {
                    "dtcpPolicySet" : {
                        "name" : "default",
                        "version" : "0"
                    },
                    "rtxControl" : True,
                    "rtxControlConfig" : {
                        "dataRxmsNmax" : 5,
                        "initialRtxTime" : 1000
                    },
                    "flowControl" : True,
                    "flowControlConfig" : {
                        "rateBased" : False,
                        "windowBased" : True,
                        "windowBasedConfig" : {
                            "maxClosedWindowQueueLength" : 10,
                            "initialCredit" : 200
                        }
                    }
                }
            }
        } ],

    "knownIPCProcessAddresses": [],

    "addressPrefixes" : [ {
            "addressPrefix" : 0,
            "organization" : "N.Bourbaki"
        }, {
            "addressPrefix" : 16,
            "organization" : "IRATI"
        } ],

    "rmtConfiguration" : {
        "pffConfiguration" : {
            "policySet" : {
                "name" : "default",
                "version" : "0"
            }
        },
        "policySet" : {
            "name" : "default",
            "version" : "1"
        }
    },

    "enrollmentTaskConfiguration" : {
        "policySet" : {
            "name" : "default",
            "version" : "1",
            "parameters" : [ {
                "name"  : "enrollTimeoutInMs",
                "value" : "10000"
            }, {
                "name"  : "watchdogPeriodInMs",
                "value" : "30000"
            }, {
                "name"  : "declaredDeadIntervalInMs",
                "value" : "120000"
            }, {
                "name"  : "neighborsEnrollerPeriodInMs",
                "value" : "0"
            }, {
                "name"  : "maxEnrollmentRetries",
                "value" : "0"
            } ]
        }
     },

    "flowAllocatorConfiguration" : {
        "policySet" : {
            "name" : "default",
            "version" : "1"
        }
    },

    "namespaceManagerConfiguration" : {
        "policySet" : {
            "name" : "default",
            "version" : "1"
        }
    },

    "securityManagerConfiguration" : {
        "policySet" : {
            "name" : "default",
            "version" : "1"
        }
    },

    "resourceAllocatorConfiguration" : {
        "pduftgConfiguration" : {
            "policySet" : {
                "name" : "default",
                "version" : "0"
            }
        }
    },

    "routingConfiguration" : {
        "policySet" : {
            "name" : "link-state",
            "version" : "1",
            "parameters" : [ {
                    "name"  : "objectMaximumAge",
                    "value" : "10000"
                },{
                    "name"  : "waitUntilReadCDAP",
                    "value" : "5001"
                },{
                    "name"  : "waitUntilError",
                    "value" : "5001"
                },{
                    "name"  : "waitUntilPDUFTComputation",
                    "value" : "103"
                },{
                    "name"  : "waitUntilFSODBPropagation",
                    "value" : "101"
                },{
                    "name"  : "waitUntilAgeIncrement",
                    "value" : "997"
                },{
                    "name"  : "routingAlgorithm",
                    "value" : "Dijkstra"
                }]
        }
    }
}

def ps_set(d, k, v, parms):
    if d[k]["name"] == v and "parameters" in d[k]:
        cur_names = [p["name"] for p in d[k]["parameters"]]
        for p in parms:
            name, value = p.split('=')
            if name in cur_names:
                for i in range(len(d[k]["parameters"])):
                    if d[k]["parameters"][i]["name"] == name:
                        d[k]["parameters"][i]["value"] = value
                        break
            else:
                d[k]["parameters"].append({ 'name': name, 'value': value })

    elif len(parms) > 0:
        d[k]["parameters"] = [ { 'name': p.split('=')[0], 'value': p.split('=')[1]} for p in parms ]

    d[k]["name"] = v

def dtp_ps_set(d, v, parms):
    for i in range(len(d["qosCubes"])):
        ps_set(d["qosCubes"][i]["efcpPolicies"], "dtpPolicySet", v, parms)

def dtcp_ps_set(d, v, parms):
    for i in range(len(d["qosCubes"])):
        ps_set(d["qosCubes"][i]["efcpPolicies"]["dtcpConfiguration"], "dtcpPolicySet", v, parms)

policy_translator = {
    'rmt.pff': lambda d, v, p: ps_set(d["rmtConfiguration"]["pffConfiguration"], "policySet", v, p),
    'rmt': lambda d, v, p: ps_set(d["rmtConfiguration"], "policySet", v, p),
    'enrollment-task': lambda d, v, p: ps_set(d["enrollmentTaskConfiguration"], "policySet", v, p),
    'flow-allocator': lambda d, v, p: ps_set(d["flowAllocatorConfiguration"], "policySet", v, p),
    'namespace-manager': lambda d, v, p: ps_set(d["namespaceManagerConfiguration"], "policySet", v, p),
    'security-manager': lambda d, v, p: ps_set(d["securityManagerConfiguration"], "policySet", v, p),
    'routing': lambda d, v, p: ps_set(d["routingConfiguration"], "policySet", v, p),
    'resource-allocator.pduftg': lambda d, v, p: ps_set(d["resourceAllocatorConfiguration"], "policySet", v, p),
    'efcp.*.dtcp': None,
    'efcp.*.dtp': None,
}

def translate_policy(difconf, path, ps, parms):
    if path in ['efcp.*.dtcp', 'efcp.*.dtp']:
        if path =='efcp.*.dtcp':
            dtcp_ps_set(difconf, ps, parms)
        else:
            dtp_ps_set(difconf, ps, parms)
    else:
        policy_translator[path](difconf, ps, parms)

