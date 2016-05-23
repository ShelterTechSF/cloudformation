from collections import defaultdict
import boto3

def map_tasks_to_services(client):
    """Return a dict from task ARNs to lists of their service ARNs"""
    clusters_p = client.get_paginator('list_clusters')
    services_p = client.get_paginator('list_services')

    t2s = defaultdict(list)
    for cp in clusters_p.paginate():
        for c in cp['clusterArns']:
            for sp in services_p.paginate(cluster=c):
                arns = sp['serviceArns']
                if len(arns) == 0: continue
                services = client.describe_services(
                    cluster=c, services=arns)
                for s in services['services']:
                    t2s[s['taskDefinition']].append((c, s['serviceArn']))
    return t2s

def buildTaskInfoDicts(client):
    """Return a 3-tuple of dicts describing the running ECS tasks in a region.

    client -- A configured boto3 ECS client

    The result is a 3-tuple of dictionaries:
    1. task ARN -> list of ARNs of services running that task
    2. image name -> list of ARNs of tasks running with that image
    3. task ARN -> dict of the task definition
    """
    t2s = map_tasks_to_services(client)
    i2t = defaultdict(list)
    t2def = {}
    for t, services in t2s.iteritems():
        resp = client.describe_task_definition(taskDefinition=t)
        t2def[t] = resp['taskDefinition']
        for cd in resp['taskDefinition']['containerDefinitions']:
            i2t[cd['image']].append(t)
    return i2t, t2def, t2s

TASK_KEYS = ['family', 'containerDefinitions', 'volumes']

def redeployImage(client, img):
    """Deploy a new (identical) revision of every ECS task running image img."""
    i2t, t2def, t2s = buildTaskInfoDicts(client)
    for t in i2t[img]:
        td = t2def[t]
        r = client.register_task_definition(**{ k: td[k] for k in TASK_KEYS })
        nt = r['taskDefinition']['taskDefinitionArn']
        for c, s in t2s[t]:
            client.update_service(cluster=c, service=s, taskDefinition=nt)

def handler(event, context):
    client = boto3.client('ecs')
    image = event['repository']['repo_name'] + ':' + event['push_data']['tag']
    redeployImage(client, image)
