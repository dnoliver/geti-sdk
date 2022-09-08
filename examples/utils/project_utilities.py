from sc_api_tools import SCRESTClient
from sc_api_tools.annotation_readers import DatumAnnotationReader
from sc_api_tools.data_models import Project
from sc_api_tools.data_models.enums import JobState
from sc_api_tools.rest_clients import PredictionClient, ProjectClient, TrainingClient
from sc_api_tools.utils import get_coco_dataset

DEMO_LABELS = ["dog"]
DEMO_PROJECT_TYPE = "detection"
DEMO_PROJECT_NAME = "COCO dog detection"


def ensure_example_project(client: SCRESTClient, project_name: str) -> Project:
    """
    Ensure that the project specified by `project_name` exists on the SonomaCreek
    instance addressed by `client`.

    :param client: SCRESTClient pointing to the SonomaCreek instance
    :param project_name: Name of the project
    :return: Project object, representing the project in SonomaCreek
    """
    project_client = ProjectClient(
        session=client.session, workspace_id=client.workspace_id
    )
    project = project_client.get_project_by_name(project_name=project_name)

    if project is None:
        # There are two options: Either the user has used the default project name
        # but has not run the `create_coco_project_single_task.py` example yet, or the
        # user has specified a different project which simply doesn't exist.
        #
        # In the first case, we create the project
        #
        # In the second case, we raise an error stating that the project doesn't exist
        # and should be created first
        if project_name == DEMO_PROJECT_NAME:
            print(
                f"\nThe project `{project_name}` does not exist on the server yet, "
                f"creating it now.... \n"
            )
            coco_path = get_coco_dataset()

            # Create annotation reader
            annotation_reader = DatumAnnotationReader(
                base_data_folder=coco_path, annotation_format="coco"
            )
            annotation_reader.filter_dataset(labels=DEMO_LABELS, criterion="OR")
            # Create project and upload data
            project = client.create_single_task_project_from_dataset(
                project_name=project_name,
                project_type=DEMO_PROJECT_TYPE,
                path_to_images=coco_path,
                annotation_reader=annotation_reader,
                labels=DEMO_LABELS,
                number_of_images_to_upload=50,
                number_of_images_to_annotate=45,
                enable_auto_train=True,
            )
        else:
            raise ValueError(
                f"The project named `{project_name}` does not exist on the server at "
                f"`{client.session.config.host}`. Please either create it first, or "
                f"specify an existing project."
            )

    ensure_project_is_trained(client, project)
    return project


def ensure_project_is_trained(client: SCRESTClient, project: Project):
    """
    Ensure that the `project` has a trained model for each task.

    :param client: SCRESTClient pointing to the SonomaCreek instance
    :param project: Project object, representing the project in SonomaCreek
    """
    prediction_client = PredictionClient(
        session=client.session, workspace_id=client.workspace_id, project=project
    )
    if prediction_client.ready_to_predict:
        print(f"\nProject '{project.name}' is ready to predict.\n")
        return

    print(
        f"\nProject '{project.name}' is not ready for prediction yet, awaiting model "
        f"training completion.\n"
    )
    training_client = TrainingClient(
        session=client.session, workspace_id=client.workspace_id, project=project
    )
    # If there are no jobs running for the project, we launch them
    jobs = training_client.get_jobs(project_only=True)
    running_jobs = [job for job in jobs if job.status.state == JobState.RUNNING]
    tasks = project.get_trainable_tasks()

    new_jobs = []
    if len(running_jobs) != len(tasks):
        for task in project.get_trainable_tasks():
            new_jobs.append(training_client.train_task(task))

    # Monitor job progress to ensure training finishes
    training_client.monitor_jobs(running_jobs + new_jobs)

    print(f"\nProject '{project.name}' is ready to predict.\n")
    return
