Feature: Classroom assistant
  The assistant answers questions about students with read-only tools.
  The browser keeps the conversation and sends it as history.

  Scenario Outline: A question with a clue uses the right tool
    Given the registry has the ten sample students
    When I ask "<question>" after a previous exchange
    Then the response status is 200
    And the answer starts with "Según el registro: "
    And the assistant took 2 steps using only the tool "<tool>"

    Examples:
      | question                        | tool                |
      | ¿Quién es STU-0003?             | get_student         |
      | ¿Quiénes están en el salón 101? | search_by_classroom |
      | ¿Quién estudia historia?        | search_by_subject   |

  Scenario: A question without clues gets the help message
    Given the registry has the ten sample students
    When I ask "Hola buenos días"
    Then the response status is 200
    And the answer is "Pregúntame por un alumno (STU-0001), un salón (salón 101) o una materia."
    And the assistant answered in 1 step without tools
    And the assistant counted 3 input tokens

  Scenario: A newly registered subject is recognized
    Given the registry has the ten sample students
    And I register "Ana Pérez" studying "Robótica" in grade 4 and classroom 120
    When I ask "¿Quién estudia robotica?"
    Then the response status is 200
    And the answer starts with "Según el registro: "
    And the assistant took 2 steps using only the tool "search_by_subject"

  Scenario: A question longer than the limit is rejected
    Given the registry allows questions of up to 10 characters
    When I ask "Hola, buenos"
    Then the response status is 422
