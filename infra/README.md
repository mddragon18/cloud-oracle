# infra/ — AWS scripts (Member 1)

Phase III only: Auto Scaling Group + ALB with `make up` / `make down` (AWS CLI
or Terraform), one region `ap-south-1`, every resource tagged `project=oracle`.

Rule from the work plan: everything in AWS is created from scripts here so it
can be torn down in one command; run `make down` after every session. Nothing
except Lambda, DynamoDB, S3 and the schedule stays up between experiment slots.
