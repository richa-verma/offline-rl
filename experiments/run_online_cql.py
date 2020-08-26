#python3
import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
import time

from absl import app
from absl import flags
import wandb

from acme import specs

from cql.agent import CQL
from acme.utils import counting
from acme import EnvironmentLoop
import sonnet as snt

# Bsuite flags
from utils import _build_environment, _build_custom_loggers

flags.DEFINE_string('environment_name', 'MiniGrid-Empty-6x6-v0', 'MiniGrid env name.')
flags.DEFINE_string('results_dir', '/tmp/bsuite', 'CSV results directory.')
flags.DEFINE_string('logs_dir', 'logs-CQL-0', 'TB logs directory')
flags.DEFINE_string('logs_tag', 'tag', 'Tag a specific run for logging in TB.')
flags.DEFINE_boolean('overwrite', False, 'Whether to overwrite csv results.')
flags.DEFINE_float('epsilon', 0.3, 'Epsilon for e-greedy actor policy.')
flags.DEFINE_float('learning_rate', 1e-3, 'Learning rate.')
flags.DEFINE_integer('samples_per_insert', 32, 'How many updates to do for each env step.')
flags.DEFINE_float('cql_alpha', 1e-3, 'Scaling parameter for the offline loss regularizer.')
flags.DEFINE_integer('n_episodes', 1000, 'Number of episodes to train for.')
flags.DEFINE_integer('n_steps', 1, 'Number of steps to bootstrap on when calculating TD(n)')
flags.DEFINE_boolean('wandb', False, 'Whether to log results to wandb.')
flags.DEFINE_string('wandb_id', '', 'Specific wandb id if you wish to continue in a checkpoint.')
flags.DEFINE_integer('batch_size', 256, 'Batch size for the learner.')
flags.DEFINE_integer('ep_max_len', 500, 'Maximum length of an episode.')
FLAGS = flags.FLAGS


def main(_):
  wb_run = wandb.init(project="offline-rl",
                      group=FLAGS.logs_tag,
                      id=FLAGS.wandb_id or str(int(time.time())),
                      config=FLAGS.flag_values_dict(),
                      reinit=FLAGS.acme_id is None) if FLAGS.wandb else None

  # Create an environment and grab the spec.
  environment = _build_environment(FLAGS.environment_name, max_steps = FLAGS.ep_max_len)
  environment_spec = specs.make_environment_spec(environment)

  network = snt.Sequential([
      snt.Flatten(),
      snt.nets.MLP([128, 64, 32, environment_spec.actions.num_values]) # TODO: try sigmoid
  ])

  disp, disp_loop = _build_custom_loggers(wb_run, FLAGS.logs_tag)

  counter = counting.Counter()
  learner_counter = counting.Counter(counter)

  # Construct the agent.
  agent = CQL(
      environment_spec=environment_spec,
      network=network,
      n_step=FLAGS.n_steps,
      epsilon=FLAGS.epsilon,
      cql_alpha=FLAGS.cql_alpha,
      samples_per_insert=FLAGS.samples_per_insert,
      learning_rate=FLAGS.learing_rate,
      counter=learner_counter,
      logger=disp)

  # Run the environment loop.
  loop = EnvironmentLoop(environment, agent, counter=counter, logger=disp_loop)
  loop.run(num_episodes=FLAGS.n_episodes)  # pytype: disable=attribute-error
  agent.save()
  artifact = wandb.Artifact('acme_checkpoint', type='model')
  dir_name = agent._learner._checkpointer._checkpoint_dir.split('checkpoints')[0]
  artifact.add_dir(dir_name)
  wb_run.log_artifact(artifact)
  wandb.run.summary.update({"checkpoint_dir": dir_name})


if __name__ == '__main__':
  app.run(main)
