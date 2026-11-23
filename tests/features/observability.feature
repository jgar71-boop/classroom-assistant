Feature: Knowing what happened to any request
  As support staff of the classroom assistant
  I want every request to carry an id that appears in the log and the metrics
  So that I can answer with data what happened to request X

  Background:
    Given an observed registry with the ten sample students

  Scenario: A response without a client id gets a generated UUID
    When I check the service health
    Then the response request id is replaced by UUID

  Scenario Outline: The client request id is kept only when it is safe
    When I check the service health with request id "<sent>"
    Then the response request id is <outcome>

    Examples:
      | sent       | outcome          |
      | demo-123   | kept             |
      | a.b_c-1    | kept             |
      | bad id {x} | replaced by UUID |

  Scenario: A question leaves a trail with the same request id and no text
    When I ask "¿Quién es STU-0003?" with request id "demo-123"
    Then the response status is 200
    And the answer body carries request_id "demo-123" like the header
    And the log has a tool_call audit for "get_student" with student_id "STU-0003"
    And the log has an agent_run for "¿Quién es STU-0003?" that stopped with "answer"
    And the log has a request event for "POST" "/ask" with status 200
    And every log line has request_id "demo-123"
    And neither "¿Quién es STU-0003?" nor the answer appears in the log

  Scenario: Registering a student is audited without the name
    When I register "Rodrigo Luna" studying "Química" in grade 9 and classroom 330
    Then the response status is 201
    And the response body is the student without request_id
    And the log has a student_created audit with grade 9 and classroom 330
    And the text "Rodrigo Luna" does not appear in the log

  Scenario: Listing students keeps the body of phase 1
    When I list the students
    Then the response status is 200
    And the response body is a list of 10 students without request_id

  Scenario: An internal failure answers 500 without leaking the message
    Given an observed registry whose storage fails with "secreto"
    When I list the students
    Then the response status is 500
    And the body is the generic internal error with the header request id
    And the log has an error event of type "RuntimeError"
    And the text "secreto" does not appear in the log

  Scenario: Metrics report the traffic and tokens of this process
    When I ask "¿Quién es STU-0003?" with request id "demo-123"
    And I read the metrics
    Then the metrics count at least 1 request
    And the metrics report input tokens above 0
    And the SLO target is 2000 ms and its result is a boolean

  Scenario: Slow requests break the latency SLO
    Given an observed registry where every request takes 3000 ms
    When I check the service health
    And I read the metrics
    Then the SLO is not met
