from __future__ import print_function

import boto3
# Unable to import module? You need to zip CRRdeployagent.py with
# cfn_resource.py!!
import cfn_resource

handler = cfn_resource.Resource()


###########Get Buckets and Agent Region #################

def get_replica_buckets(client, list_buckets):
    """
    :Args:

      client: boto3 s3 client
      list_buckets: a list of bucket objects

    :Returns:

      replica_buckets: list of destination buckets

      source_buckets: list of names of the buckets with CRR enabled
    """
    print('List Replica Buckets:')
    try:
        replica_buckets = []
        source_buckets = []
        for bucket in list_buckets:
            bucket_response = get_bucket_replication(bucket['Name'], client)
            if 'ReplicationConfigurationError-' != bucket_response \
                    and bucket_response['ReplicationConfiguration']['Rules'][0]['Status'] != 'Disabled':
                source_buckets.append(bucket['Name'])
                dest_bucket_arn = bucket_response['ReplicationConfiguration']['Rules'][0]['Destination']['Bucket']
                replica_buckets.append(dest_bucket_arn.split(':',5)[5])
    except Exception as e:
        print(e)
        raise e
    return replica_buckets, source_buckets

def comma_delimited_to_list(cd_list):
    """converts a comma delimited list string to a list object"""
    return [
        bucket_name.strip() for bucket_name in cd_list.split(',')
    ]

def get_bucket_replication(bucket_name,client):
    try:
        response = client.get_bucket_replication(
            Bucket=bucket_name
        )
    except Exception as e:
        print(e)
        response = "ReplicationConfigurationError-"
    return response

def get_source_buckets(buckets_prop):
    client = boto3.client('s3')
    all_buckets = client.list_buckets()['Buckets']
    if buckets_prop == 'ALL':
        final_bucket_list = all_buckets
    else:
        print("CUSTOM BUCKET LIST {}".format(buckets_prop))
        input_bucket_list = comma_delimited_to_list(buckets_prop)
        final_bucket_list = []
        for bucket in all_buckets:
            if bucket['Name'] in input_bucket_list:
                final_bucket_list.append(bucket)
    return final_bucket_list

#Gets the list of agent regions for Agent deployment

def get_agent_regions(src_bucket_list):
    print('AgentRegionList:')
    try:
        client = boto3.client('s3')
        replica_buckets, source_buckets = get_replica_buckets(client, src_bucket_list)
        agent_set = set([])
        for bucket in replica_buckets:
            response = client.get_bucket_location(
                Bucket=bucket
            )
            region = response['LocationConstraint']
            if region is None:
                agent_set.add('us-east-1') ## Location constraint for all us-east bucket returns a null as in S3
            else:
                agent_set.add(region)
        for bucket in source_buckets:
            response = client.get_bucket_location(
                Bucket=bucket
            )
            region = response['LocationConstraint']
            if region is None:
                agent_set.add('us-east-1') ## Location constraint for all us-east bucket returns a null as in S3
            else:
                agent_set.add(region)
        agent_regions = list(agent_set)
        print(agent_regions)
    except Exception as e:
        print(e)
        raise e
    return agent_regions

# =====================================================================
# CREATE
#
@handler.create

def create_agent(event, context):

    topic_name = event["ResourceProperties"]["Topic"] # SNS topic
    queue_arn = event["ResourceProperties"]["CRRQueueArn"] # URL of the SQS Queue
    table_name = event["ResourceProperties"]["CRRMonitorTable"]
    monitor_region = event['ResourceProperties']['MonitorRegion']
    buckets_prop = event['ResourceProperties']['buckets']

    final_bucket_list = get_source_buckets(buckets_prop)

    ##Enable time to Live for DynamoDB table CRRMonitor
    time_to_live(table_name, monitor_region)

    agent_regions = get_agent_regions(final_bucket_list)
    # Default value for returning resourceid
    physical_resource_id = {
        'PhysicalResourceId': 'CRRMonitorAgent-us-east-1'
    }

    for region in agent_regions:
        physical_resource_id = agent_creator(region, topic_name, queue_arn)

    return physical_resource_id

def time_to_live(table_name, region):
    # -----------------------------------------------------------------
    # Create client connections
    #
    try:
        client = boto3.client(service_name='dynamodb', region_name=region)

        response = client.update_time_to_live(
            TableName=table_name,
            TimeToLiveSpecification={
                'Enabled': True,
                'AttributeName': 'itemttl'
            }
        )

    except Exception as e:
        print(e)
        print('Error enabling itemttl')
        raise e

def agent_creator(agt_region, topic_name, queue_arn):

    boto3.setup_default_session(region_name=agt_region)

    topic = topic_name + "-" + agt_region
    print("Deploy " + topic + " to " + agt_region)

    # -----------------------------------------------------------------
    # Create client connections
    #
    try:
        cwe = boto3.client('events')
        sns = boto3.client('sns')
    except Exception as e:
        print(e)
        print('Error creating clients for ' + agt_region)
        raise e

    # -----------------------------------------------------------------
    # Note: duplication is not a concern - we will replace the rule and
    # topic if they already exist
    #
    # Create the CloudWatch Event rule in a disabled state.
    # Create an SNS topic
    # Add a target to the rule to send to the new SNS topic
    # Enable the rule
    try:
        cwe.put_rule(
            Description='Fires CRRMonitor for S3 events that indicate an object has been stored.',
            Name='CRRAgent',
            EventPattern="{ \"detail-type\": [ \"AWS API Call via CloudTrail\" ], \"detail\": { \"eventSource\": [ \"s3.amazonaws.com\"], \"eventName\": [ \"PutObject\", \"CopyObject\", \"CompleteMultipartUpload\" ] } }",
            State='DISABLED'
        )
        topicarn=sns.create_topic(Name=topic)['TopicArn']
        sns.set_topic_attributes(
            TopicArn=topicarn,
            AttributeName='Policy',
            AttributeValue='{\
        "Version": "2012-10-17",\
        "Id": "CWEventPublishtoTopic",\
        "Statement": [\
            {\
              "Sid": "CWEventPublishPolicy",\
              "Action": [\
                "SNS:Publish"\
              ],\
              "Effect": "Allow",\
              "Resource": "' + topicarn + '",\
              "Principal": {\
                "Service": [\
                  "events.amazonaws.com"\
                ]\
              }\
            }\
          ]\
        }\
                ',

        )
        cwe.put_targets(
            Rule='CRRAgent',
            Targets=[
                {
                    'Id': 'CRRAgent-' + agt_region,
                    'Arn': topicarn
                }
            ]
        )
        cwe.enable_rule( Name='CRRAgent' )
    except Exception as e:
        print(e)
        print('Error creating SNS topic and CW Event rule: ' + topic)
        raise e

    # -----------------------------------------------------------------
    # Create cross-region Queue subscription from the SNS end
    #
    try:
        response=sns.subscribe(
            TopicArn=topicarn,
            Protocol='sqs',
            Endpoint=queue_arn
        )

    except Exception as e:
        print(e)
        print('Error subscribing SNS topic ' + topic + ' to SQS Queue ' + queue_arn)
        raise e

    return { 'Data': { 'TopicArn': topicarn }, 'PhysicalResourceId': 'CRRMonitorAgent-' + agt_region}


# =====================================================================
# UPDATE
#
@handler.update
def update_agent(event, context):
    topic_name = event["ResourceProperties"]["Topic"] # SNS topic
    queue_arn = event["ResourceProperties"]["CRRQueueArn"] # URL of the SQS Queue
    table_name = event["ResourceProperties"]["CRRMonitorTable"]
    monitor_region = event['ResourceProperties']['MonitorRegion']
    buckets_prop = event['ResourceProperties']['buckets']

    final_bucket_list = get_source_buckets(buckets_prop)

    agent_regions = get_agent_regions(final_bucket_list)
    # Default value for returning resourceid
    physical_resource_id = {
        'PhysicalResourceId': 'CRRMonitorAgent-us-east-1'
    }

    for region in agent_regions:
        physical_resource_id = agent_creator(region, topic_name, queue_arn)

    return physical_resource_id


# =====================================================================
# DELETE
#
@handler.delete
def delete_agent(event, context):
    buckets_prop = event['ResourceProperties']['buckets']
    final_bucket_list = get_source_buckets(buckets_prop)
    agent_regions = get_agent_regions(final_bucket_list)
    topic_name = event["ResourceProperties"]["Topic"] # SNS topic

    for region in agent_regions:
        agent_deleter(region, topic_name)

    return {}


def agent_deleter(agt_region, topic_name):

    boto3.setup_default_session(region_name=agt_region)
    topic = topic_name + "-" + agt_region
    print("Delete " + topic + " in " + agt_region)
    # -----------------------------------------------------------------
    # Create client connections
    #
    # events
    try:
        cwe = boto3.client('events')
        sns = boto3.client('sns')
        sts = boto3.client('sts')
    except Exception as e:
        print(e)
        print('Error creating Events client for ' + agt_region)
        raise e

    # -----------------------------------------------------------------
    # RequestType Delete
    #
    myaccount = sts.get_caller_identity()['Account']
    topicarn = 'arn:aws:sns:' + agt_region + ':' + myaccount + ':' + topic
    # -----------------------------------------------------------------
    # Remove the Targets
    #
    cwe.remove_targets(
        Rule='CRRAgent',
        Ids=[
            'CRRAgent-' + agt_region,
        ]
    )
    # Delete the SNS topic
    sns.delete_topic(
        TopicArn=topicarn
    )
    # Delete the CW rule
    cwe.delete_rule(
        Name='CRRAgent'
    )

    return {}
