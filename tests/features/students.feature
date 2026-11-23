Feature: Student registry
  The school staff registers students and looks them up through the API.
  Students live in a JSON file that is read on every request.

  Scenario: A valid student is registered with the next id
    Given the registry has the ten sample students
    When I register "  Ana Pérez  " studying "  Música " in grade 4 and classroom 120
    Then the response status is 201
    And the saved student has id "STU-0011", name "Ana Pérez" and subject "Música"
    And the student list is sorted by id and ends with "STU-0011"

  Scenario: The first student creates the registry file
    Given the registry file does not exist yet
    When I register "Ana Pérez" studying "Música" in grade 4 and classroom 120
    Then the response status is 201
    And the saved student has id "STU-0001", name "Ana Pérez" and subject "Música"
    And the registry file exists

  Scenario Outline: An invalid student is rejected
    Given the registry has the ten sample students
    When I register a student whose <field> is <value>
    Then the response status is 422
    And the registry still has 10 students

    Examples:
      | field     | value   |
      | classroom | missing |
      | name      | "   "   |
      | classroom | 1000    |
      | classroom | "101"   |
      | grade     | 3.5     |

  Scenario: Filters by classroom and subject are combined
    Given the registry has the ten sample students
    And I register "Ana Pérez" studying "Matemáticas" in grade 3 and classroom 204
    When I list the students of classroom 101 studying "MATEMATICAS"
    Then the response status is 200
    And the listed ids are "STU-0001, STU-0002, STU-0008"

  Scenario: An unknown student is reported
    Given the registry has the ten sample students
    When I look up the student "STU-0099"
    Then the response status is 404
    And the error detail is "Student not found"

  Scenario: A student written to the file by hand is visible at once
    Given the registry has the ten sample students
    When someone adds the student "STU-0050" directly to the file
    And I look up the student "STU-0050"
    Then the response status is 200
