from __future__ import print_function

import boto3

# Unable to import module? You need to zip CRRdeployagent.py with
# cfn_resource.py!!
import cfn_resource

handler = cfn_resource.Resource()

client = {
    'cloudtrail': {
        'service': 'cloudtrail'
    },
    'cloudwatch': {
        'service': 'cloudwatch'
    },
    's3': {
        'service': 's3'
    }
}



# =====================================================================
# connect_clients
# ---------------
# Connect to all the clients. We will do this once per instantiation of
# the Lambda function (not per execution)
# =====================================================================
def connect_clients(clients_to_connect):
    for c in clients_to_connect:
        try:
            if 'region' in clients_to_connect[c]:
                clients_to_connect[c]['handle'] = boto3.client(
                    clients_to_connect[c]['service'],
                    region_name=clients_to_connect[c]['region'])
            else:
                clients_to_connect[c]['handle'] = boto3.client(
                    clients_to_connect[c]['service'])
        except Exception as e:
            print(e)
            print('Error connecting to ' + clients_to_connect[c]['service'])
            raise e
    return clients_to_connect

def validate_trail(trail_name):
    """Validates that the trail exists"""
    print('Validating Trail: ')
    try:
        response = client['cloudtrail']['handle'].describe_trails(
            trailNameList=[trail_name]
        )
        key_list = [
            'IncludeGlobalServiceEvents',
            'IsMultiRegionTrail',
            'LogFileValidationEnabled'
        ]
        for key in key_list:
            if not response['trailList'][0].get(key):
                raise ValueError(
                    "Trail {0} must have {1} set to true".format(
                        trail_name, key))
    except Exception as e:
        print('Error validating trail {}'.format(str(e)))
        raise e


def get_buckets(list_buckets):
    """
    :Args:

      list_buckets: a list of bucket objects

    :Returns:

      crr_buckets: list of source and destination bucket ARNs (for buckets that have CRR enabled)

      bucket_names: list of names of the buckets with CRR enabled

    """
    print('List Buckets:')
    try:
        crr_buckets = [] # list of bucket objects with CRR enabled
        bucket_names = [] # list of bucket names with CRR enabled
        for bucket in list_buckets:
            bucket_response = get_bucket_replication(bucket['Name'])
            if ('ReplicationConfigurationError-' != bucket_response
                    and bucket_response['ReplicationConfiguration']['Rules'][0]
                    ['Status'] != 'Disabled'):
                bucket_names.append(bucket['Name'])
                crr_buckets.append(get_source_bucket_arn(bucket['Name']))
                crr_buckets.append(get_replica_bucket_arn(bucket_response))
    except Exception as e:
        print(e)
        raise e
    return crr_buckets, bucket_names


def get_bucket_replication(bucket_name):
    try:
        response = client['s3']['handle'].get_bucket_replication(
            Bucket=bucket_name
        )
    except Exception as e:
        print(e)
        response = "ReplicationConfigurationError-"
    return response

def get_source_bucket_arn(response):
    try:
        # source_bucket = response['ReplicationConfiguration']['Rules'][0]['ID']
        # src_bucket = 'arn:aws:s3:::' + source_bucket
        # if response['ReplicationConfiguration']['Rules'][0]['Prefix'] == '':
        #     src_bucket = src_bucket + '/'
        src_bucket = 'arn:aws:s3:::' + response + '/'
    except Exception as e:
        print(e)
        print('SourceBucket')
        raise e
    return src_bucket

def get_replica_bucket_arn(response):
    try:
        dest_bucket_arn = response['ReplicationConfiguration']['Rules'][0]['Destination']['Bucket']
        dest_bucket_prefix = response['ReplicationConfiguration']['Rules'][0]['Prefix']
        replica_bucket = dest_bucket_arn + '/' + dest_bucket_prefix
    except Exception as e:
        print(e)
        print('ReplicaBucket')
        raise e
    return replica_bucket

def put_event_selectors(trail_name, crr_buckets):
    print('Data Events: ')
    try:

        client['cloudtrail']['handle'].put_event_selectors(
            TrailName=trail_name,
            EventSelectors=[
                {
                    'ReadWriteType': 'All',
                    'IncludeManagementEvents': True,
                    'DataResources': [
                        {
                            'Type': 'AWS::S3::Object',
                            'Values': crr_buckets
                        },
                    ]
                }
            ]
        )
    except Exception as e:
        print(e)
        print('Data Events Trail')
        raise e

def put_metric_alarm(sns_topic, src_buckets):
    print('Metric Alarms:')
    try:
        for bucket in src_buckets:
            client['cloudwatch']['handle'].put_metric_alarm(
                AlarmName='FailedReplicationAlarm-' + bucket,
                AlarmDescription='Trigger an alarm for Failed Replication Objects.',
                ActionsEnabled=True,
                AlarmActions=[
                    sns_topic,
                ],
                MetricName='FailedReplications',
                Namespace='CRRMonitor',
                Statistic='Sum',
                Dimensions=[
                    {
                        'Name': 'SourceBucket',
                        'Value': bucket
                    },
                ],
                Period=60,
                EvaluationPeriods=1,
                Threshold=0.0,
                ComparisonOperator='GreaterThanThreshold'

            )
    except Exception as e:
        print(e)
        print('Data Events Trail')
        raise e

def put_metric_data(src_buckets):
    print('Metric Data: ')
    try:
        for bucket in src_buckets:
            client['cloudwatch']['handle'].put_metric_data(
                Namespace='CRRMonitor',
                MetricData=[
                    {
                        'MetricName': 'FailedReplications',
                        'Dimensions': [
                            {
                                'Name': 'SourceBucket',
                                'Value': bucket
                            },
                        ],
                        'Value': 0.0
                    },
                ]
            )
    except Exception as e:
        print(e)
        print('Data Events Trail')
        raise e


def comma_delimited_to_list(cd_list):
    """converts a comma delimited list to a list object"""
    return [
        bucket_name.strip() for bucket_name in cd_list.split(',')
    ]


def setup_monitored_buckets(event):
    """
    This function executes common code for `handler.create` and
    `handler.update`
    """
    trail_name = event["ResourceProperties"]["trail_name"] # Trail Name
    sns_topic_arn = event["ResourceProperties"]["sns_topic_arn"] # SNS Topic
    buckets_prop = event['ResourceProperties']['buckets']
    all_buckets = client['s3']['handle'].list_buckets()['Buckets']
    if buckets_prop == 'ALL':
        final_bucket_list = all_buckets
    else:
        print("CUSTOM BUCKET LIST {}".format(buckets_prop))
        input_bucket_list = comma_delimited_to_list(buckets_prop)
        final_bucket_list = []
        for bucket in all_buckets:
            if bucket['Name'] in input_bucket_list:
                final_bucket_list.append(bucket)

    crr_buckets, bucket_names = get_buckets(final_bucket_list)
    crr_buckets = list(set(crr_buckets))

    print("BUCKETS TO MONITOR {}".format(crr_buckets))

    ### Trail Validation

    validate_trail(trail_name)

    put_event_selectors(trail_name, crr_buckets)

    ### Metric Alarm

    put_metric_data(bucket_names) # Source buckets are derived from get_buckets() call

    if event.get('RequestType') == 'Update':
        remove_old_alarms([bucket['Name'] for bucket in final_bucket_list])
    put_metric_alarm(sns_topic_arn, bucket_names)


def remove_old_alarms(buckets):
    """Removes alarms for buckets that are no longer being monitored"""
    alarm_name_prefix = 'FailedReplicationAlarm-'
    alarms = client['cloudwatch']['handle'].describe_alarms(
        AlarmNamePrefix=alarm_name_prefix).get('MetricAlarms', [])

    alarms_to_delete = []

    for alarm in alarms:
        bucket_name = alarm['AlarmName'].split(alarm_name_prefix)[-1]
        if bucket_name not in buckets:
            alarms_to_delete.append(alarm['AlarmName'])
    if alarms_to_delete:
        print("Deleting alarms {}".format(alarms_to_delete))
        client['cloudwatch']['handle'].delete_alarms(
            AlarmNames=alarms_to_delete)

# =====================================================================
# CREATE
#
@handler.create
def create_trail_alarm(event, context):
    """handler to create CustomTrailAlarm resource"""
    print("CREATE EVENT {}".format(event))
    setup_monitored_buckets(event)
    return {'PhysicalResourceId': 'CRRMonitorTrailAlarm'}

###### M A I N ######
client = connect_clients(client)


# =====================================================================
# UPDATE
#
@handler.update
def update_trail_alarm(event, context):

    # 1) put_event_selectors for new buckets, remove event selectors for buckets that are no longer being monitored
    # 2) Put Metric Data for newly added buckets for monitoring
    # 3) update metric alarms, remove old ones keep existing ones
    print("UPDATE EVENT {}".format(event))
    setup_monitored_buckets(event)
    return {'PhysicalResourceId': 'CRRMonitorTrailAlarm'}


# =====================================================================
# DELETE
#
@handler.delete
def delete_trail_alarm(event, context):
    buckets_prop = event['ResourceProperties']['buckets']
    trail_name = event['ResourceProperties']['trail_name']
    # -----------------------------------------------------------------
    # Create client connections
    #
    # events
    print("DELETE EVENT {}".format(event))
    try:
        cwe = boto3.client('cloudwatch')

    except Exception as e:
        print(e)
        print('Error creating Events client')
        raise e

    all_buckets = client['s3']['handle'].list_buckets()['Buckets']

    if buckets_prop == 'ALL':
        source_bucket_list = all_buckets
    else:
        print("CUSTOM BUCKET LIST {}".format(buckets_prop))
        input_bucket_list = comma_delimited_to_list(buckets_prop)
        final_bucket_list = []
        for bucket in all_buckets:
            if bucket['Name'] in input_bucket_list:
                final_bucket_list.append(bucket)
        source_bucket_list = final_bucket_list

    # remove event selectors by sending empty list of buckets
    put_event_selectors(trail_name, [])

    for bucket in source_bucket_list:
        alarm_name = 'FailedReplicationAlarm-' + bucket['Name']
        cwe.delete_alarms(
            AlarmNames=[
                alarm_name
            ]
        )
        print('Deleted alarm {}'.format(alarm_name))

    return {}
