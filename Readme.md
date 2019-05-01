# python-crr-monitor

A solution describing S3 Cross Region Replication Monitoring. This solution is based on the [AWS
Solution](https://docs.aws.amazon.com/solutions/latest/crr-monitor/overview.html)

## Overview
Amazon Simple Storage Service (Amazon S3) offers cross-region replication, a bucket-level feature that enables automatic, asynchronous copying of objects across buckets in different AWS Regions. This feature can help companies minimize latency when accessing objects in different geographic regions, meet compliance requirements, and for operational purposes. Amazon S3 encrypts all data in transit across AWS Regions using SSL, and objects in the destination bucket are exact replicas of objects in the source bucket. For more information on cross-region replication, see the Amazon S3 Developer Guide.

Currently, AWS customers can retrieve the replication status of their objects manually or use an Amazon S3 inventory to generate metrics on a daily or weekly basis. To help customers more proactively monitor the replication status of their Amazon S3 objects, AWS offers the Cross-Region Replication Monitor (CRR Monitor) solution. The CRR Monitor automatically checks the replication status of Amazon S3 objects across all AWS Regions in a customers’ account, providing near real-time metrics as well as failure notifications to help customers proactively identify failures and troubleshoot problems. The solution automatically provisions the necessary AWS services to monitor and view replication status, including AWS Lambda, Amazon CloudWatch, Amazon Simple Notification Service (Amazon SNS), AWS CloudTrail and Amazon DynamoDB, and offers an option to use Amazon Kinesis Firehose to archive replication metadata in Amazon S3.

## Abstract
CRRMonitor is a serverless tool for monitoring replication of objects between a source and destination bucket and elapsed time of replicated objects.
CRR Monitor provides ability to get insights of objects at adhoc basis.

## CloudFormation Templates
- `original-aws-crr-monitor.template` which is the original template offered by the AWS Solution
- `crr-monitor.yml` which is a modified version of `original-aws-crr-monitor.template`

## Lambda Scripts
- CRRdeployagent/CRRdeployagent.py
- CRRMonitorTrailAlarm/CRRMonitorTrailAlarm.py
- CRRMonitor.py
- CRRHourlyMaint.py
- CRRMonitorHousekeeping.py
- CRRBucketStatus.py

## CloudWatch Metrics
Under the `CRRMonitor` namespace, you will find the following metrics:

- Source - Destination Bucket Metrics
    - `ReplicationSpeed`: the rate (bytes/sec) at which object data is being replicated in the last 5 minutes
    - `ReplicationObjects`: the number of objects that have been replicated in the last 5 minutes

- Source Bucket Metrics
    - `FailedReplications`: the number of objects from the source bucket that failed to replicate in the last 5 minutes

## Datadog Metrics Integration
Please find the information below regarding integration your AWS Account(s) with Datadog to utilize the CRR Monitor Metrics:

 - Integration Setup
    - Currently, `tax-preprod` and `prod` AWS accounts' services have been integrated and Datadog is automatically collecting custom metrics and alarms from CloudWatch. Use this [document](https://thehub.thomsonreuters.com/docs/DOC-2574616-datadog-aws-integration) for instructions and other information

 - Creating Dashboards
    - You can create your own timeboards based on the metrics mentioned above. The naming convention for those metrics is as follows: `<cloudwatch_namespace_lowercase>.<metric_name_case_sensitive>`. For instructions on how to create Datadog timeboards click [here](https://docs.datadoghq.com/graphing/dashboards/timeboard/)
    - By default, the CloudWatch namespace is `CRRMonitor` so for example, to find the `ReplicationObjects` metric in Datadog when trying to add a graph, search for the metric `crrmonitor.ReplicationObjects`
    - You can also plot these metrics based on the [dimensions](#cloudwatch-metrics) by using the `from` option when adding a metric to a graph in your timeboard

## Original Source Code Reference
For the reference source code, please click [here](https://github.com/awslabs/aws-crr-monitor)
