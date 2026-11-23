Feature: Cheaper answers without worse answers
  As the person who pays for the classroom assistant
  I want every answer to choose the cheapest model that can handle it and report its cost
  So that I can lower the bill and prove that quality did not drop

  Scenario: A simple question is answered by the small model and has a cost
    Given a priced registry with the default settings
    When I ask "¿Quién es STU-0003?"
    Then the response status is 200
    And the answer used the small model with route "short_question"
    And the answer cost matches the small model prices with 0 cached calls

  Scenario Outline: The router picks the model with a rule in code
    Given a priced registry where ROUTING is "<routing>"
    When I ask "<question>"
    Then the response status is 200
    And the answer used the <size> model with route "<route>"

    Examples:
      | routing | question                              | size  | route            |
      | true    | ¿POR QUE hay alumnos en el salón 101? | large | keyword:por qué  |
      | true    | Explícame quién es STU-0003           | large | keyword:explica  |
      | true    | Dame métodos de estudio               | small | short_question   |
      | false   | ¿Quién es STU-0003?                   | large | routing_disabled |

  Scenario Outline: Only questions longer than ROUTER_MAX_CHARS go to the large model
    Given a priced registry with the default settings
    When I ask a question of <length> characters
    Then the response status is 200
    And the answer used the <size> model with route "<route>"

    Examples:
      | length | size  | route          |
      | 81     | large | long_question  |
      | 80     | small | short_question |

  Scenario Outline: Only the last HISTORY_WINDOW messages reach the model
    Given a spied registry where HISTORY_WINDOW is "<window>"
    When I ask "Hola" with 10 history messages
    Then the response status is 200
    And the model received <count> messages on its first call

    Examples:
      | window | count |
      | 2      | 3     |
      | 0      | 1     |

  Scenario: Metrics add up the cost of answers but not of registrations
    Given a priced registry with the default settings
    When I ask "¿Quién es STU-0003?"
    And I ask "Compara los salones 101 y 204"
    Then the metrics cost_usd is the sum of the answer costs
    When I register "Ana Pérez" studying "Música" in grade 4 and classroom 120
    Then the metrics cost_usd is the sum of the answer costs

  Scenario: The agent_run log carries model, route and cost without the question
    Given a priced registry with the default settings
    When I ask "¿Quién es STU-0003?"
    Then the agent_run log has the model, route and cost of the answer
    And the text "¿Quién es STU-0003?" does not appear in the log

  Scenario: An unavailable model answers 502 with the request id
    Given a priced registry whose model is unavailable
    When I ask "¿Quién es STU-0003?"
    Then the response status is 502
    And the body is "model unavailable" with the header request id
    And the log has an error event of type "ModelUnavailable"
    And the metrics error rate is above 0
