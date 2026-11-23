Feature: Only clients with a key reach the student data
  As the person who publishes the classroom assistant
  I want every client to present its own key and respect a request limit
  So that nobody without a key sees the names of the students

  Background:
    Given a secured registry with the ten sample students

  Scenario: Every protected route rejects a visitor without a key
    When a visitor without a key calls every protected route
    Then every call answers 401 with "invalid or missing API key"
    And the registry still has the ten sample students

  Scenario: A wrong key cannot ask the assistant
    When I ask "¿Quién es STU-0003?" with the key "wrong-key-0000000000"
    Then the response status is 401
    And the body detail is "invalid or missing API key"

  Scenario: The public pages stay open without a key
    When a visitor without a key opens the public pages
    Then every public page answers 200

  Scenario: A valid key works and its client name is logged
    When I register "Rodrigo Luna" studying "Química" in grade 9 and classroom 330
    And I ask "¿Quién es STU-0003?" with my key
    And a visitor without a key checks the service health
    Then the question succeeded and the registry has 11 students
    And the log names the client "teacher" in request, agent_run and both audits
    And the health request event has no client

  Scenario: The key never appears in the log or in the errors
    Given a secured registry limited to 1 request per minute whose model is down
    When I ask "hola" with my key
    And I ask "hola" with my key
    And I ask "hola" with the key "wrong-key-0000000000"
    Then the answers had the statuses 502, 429 and 401
    And no key appears in the log, the bodies or the error output

  Scenario: The rate limit is counted per client and per minute
    Given a secured registry limited to 2 requests per minute on a manual clock
    When the client "teacher" asks 3 questions
    Then the last answer is 429 "rate limit exceeded" with a positive Retry-After
    And the client "office" can still ask
    And after 61 seconds the client "teacher" can ask again

  Scenario: A rejected request is still traced and counted
    When I ask "hola" without a key
    Then the response status is 401
    And the response has an X-Request-ID header
    And the metrics count 1 request
